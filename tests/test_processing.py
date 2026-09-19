import json
from datetime import datetime

import pytest
from conftest import plan_for, receipt_for

from vault_retrieval.common import VaultError, digest
from vault_retrieval.coordinator import Coordinator, next_trigger


def test_scheduled_end_to_end(env):
    service, key, _ = env
    coordinator = Coordinator(service)
    original = service.config.read("Study/Raw/Capture.md")
    first = coordinator.run_intake()
    assert first["needs_planning"]
    service.extract_documents([item["document_id"] for item in first["pending"]])
    run = coordinator.run_intake(plan_for(service))
    ident = run["proposal_id"]
    assert len(run["notifications"]) == 1
    coordinator.acknowledge(ident)
    repeat = coordinator.run_intake()
    assert repeat["quiet"] and not repeat["needs_planning"]
    assert not (service.config.vault / "Study/Notes/Linear systems.md").exists()
    with pytest.raises(VaultError, match="approval"):
        coordinator.apply(ident, {"approved": True})
    result = coordinator.apply(ident, receipt_for(service, key, ident))
    assert result["state"] == "completed"
    registry = json.loads(service.config.read("Planning/Processing log.json"))
    assert registry["custom"] == "preserve me"
    assert registry["sources"][0]["sha256"] == digest(original)
    assert registry["sources"][0]["outputs"] == ["Study/Notes/Linear systems.md"]
    assert service.config.read("Study/Raw/Capture.md") == original
    assert coordinator.run_intake()["quiet"]
    assert coordinator.apply(ident, receipt_for(service, key, ident))["already_applied"]
    assert len(registry["completed_batches"]) == 1


def test_partial_failure_recovery(env):
    service, key, _ = env
    service.refresh()
    c = Coordinator(service)
    ident = c.propose(plan_for(service))["id"]
    receipt = receipt_for(service, key, ident)
    with pytest.raises(VaultError, match="Injected"):
        c.apply(ident, receipt, fail_after=1)
    assert (service.config.vault / "Study/Notes/Linear systems.md").exists()
    assert not json.loads(service.config.read("Planning/Processing log.json"))["sources"]
    assert (
        service.db.execute("SELECT state FROM proposals WHERE id=?", (ident,)).fetchone()[0]
        == "applying"
    )
    assert c.apply(ident, receipt)["state"] == "completed"


def test_conflict_preflight_and_source_change(env):
    service, key, _ = env
    service.refresh()
    c = Coordinator(service)
    ident = c.propose(plan_for(service))["id"]
    receipt = receipt_for(service, key, ident)
    target = service.config.vault / "Study/Notes/Linear systems.md"
    target.write_text("user's competing note")
    with pytest.raises(VaultError, match="target"):
        c.apply(ident, receipt)
    assert target.read_text() == "user's competing note"
    target.unlink()
    (service.config.vault / "Study/Raw/Capture.md").write_text("new source")
    with pytest.raises(VaultError, match="Source revision"):
        c.apply(ident, receipt)
    assert not target.exists()


def test_plan_grounding_and_protected_original(env):
    service, _, data = env
    service.refresh()
    c = Coordinator(service)
    plan = plan_for(service)
    data["user_note_paths"] = []
    with pytest.raises(VaultError, match="provenance"):
        c.propose(plan)
    data["user_note_paths"] = ["Study/Raw/Capture.md"]
    plan["changes"][0]["path"] = "Study/Raw/Capture.md"
    with pytest.raises(VaultError):
        c.propose(plan)


def test_notification_retry_and_pending_rebuild(env):
    service, _, _ = env
    service.refresh()
    c = Coordinator(service)
    ident = c.propose(plan_for(service))["id"]
    assert c.run_intake()["notifications"][0]["delivery_key"] == ident
    service.refresh(rebuild=True)
    assert c.run_intake()["notifications"][0]["delivery_key"] == ident
    c.acknowledge(ident)
    assert c.run_intake()["notifications"] == []
    assert service.db.execute("SELECT count(*) FROM proposals").fetchone()[0] == 1


def test_dst_schedule():
    assert (
        next_trigger(datetime.fromisoformat("2026-03-06T18:00:00+00:00"))
        == "2026-03-08T12:10:00-04:00"
    )
    assert (
        next_trigger(datetime.fromisoformat("2026-10-30T18:00:00+00:00"))
        == "2026-11-01T12:10:00-05:00"
    )


def test_multi_file_create_update_log_and_no_duplicate(env):
    service, key, _ = env
    target = service.config.vault / "Study/Notes/Existing.md"
    target.write_text("---\nstatus: draft\n---\nExisting explanation.\n")
    service.refresh()
    plan = plan_for(service)
    updated = (
        target.read_text()
        + "\nSource: [[Study/Raw/Capture.md]]\nSee [[Study/Notes/Linear systems.md]].\n"
    )
    plan["changes"].append(
        {
            "path": "Study/Notes/Existing.md",
            "expected_hash": digest(target.read_bytes()),
            "content": updated,
        }
    )
    plan["sources"][0]["outputs"].append("Study/Notes/Existing.md")
    c = Coordinator(service)
    ident = c.propose(plan)["id"]
    c.apply(ident, receipt_for(service, key, ident))
    assert target.read_text() == updated
    assert c.run_intake()["pending"] == []
    assert service.neighbors(service.search("Gaussian")[0]["document_id"], "outputs")


def test_changed_registry_supersedes_and_can_replan(env):
    service, _, _ = env
    service.refresh()
    c = Coordinator(service)
    plan = plan_for(service)
    old = c.propose(plan)["id"]
    path = service.config.vault / "Planning/Processing log.json"
    registry = json.loads(path.read_text())
    registry["owner_field"] = "new information"
    path.write_text(json.dumps(registry))
    new = c.propose(plan)["id"]
    assert new != old
    assert (
        service.db.execute("SELECT state FROM proposals WHERE id=?", (old,)).fetchone()[0]
        == "superseded"
    )


def test_faithful_raw_companion_recovers_and_is_not_intake(env):
    service, key, data = env
    data["companion_roots"] = ["Study/Raw"]
    service.refresh()
    plan = plan_for(service)
    plan["sources"][0]["outputs"] = ["Study/Raw/Derived companion.md"]
    plan["changes"][0]["path"] = "Study/Raw/Derived companion.md"
    plan["changes"][0]["content"] = plan["changes"][0]["content"].replace(
        "status: draft", "status: draft\nderived_companion: true"
    )
    c = Coordinator(service)
    ident = c.propose(plan)["id"]
    receipt = receipt_for(service, key, ident)
    with pytest.raises(VaultError, match="Injected"):
        c.apply(ident, receipt, fail_after=1)
    c.apply(ident, receipt)
    assert c.run_intake()["pending"] == []


def test_raw_first_and_concurrent_trigger_lock(env):
    service, _, _ = env
    (service.config.vault / "Study/documents/A.md").write_text("# Outside Raw\nStudy document.\n")
    c = Coordinator(service)
    result = c.run_intake()
    assert result["pending"][0]["source_role"] == "raw"
    with service.store.lock():
        with pytest.raises(VaultError, match="Another operation"):
            c.run_intake()


def test_tampered_approval_and_changed_output_after_interruption(env):
    service, key, _ = env
    service.refresh()
    c = Coordinator(service)
    ident = c.propose(plan_for(service))["id"]
    receipt = receipt_for(service, key, ident)
    bad = json.loads(json.dumps(receipt))
    bad["message"]["proposal_digest"] = "0" * 64
    with pytest.raises(VaultError, match="approval"):
        c.apply(ident, bad)
    with pytest.raises(VaultError, match="Injected"):
        c.apply(ident, receipt, fail_after=1)
    target = service.config.vault / "Study/Notes/Linear systems.md"
    target.write_text("New human edits after interruption")
    with pytest.raises(VaultError, match="target"):
        c.apply(ident, receipt)
    assert target.read_text() == "New human edits after interruption"
    assert not json.loads(service.config.read("Planning/Processing log.json"))["sources"]


def test_registry_update_preserves_metadata_and_timestamp_field(env):
    service, key, _ = env
    log = service.config.vault / "Planning/Processing log.json"
    before = json.loads(log.read_text())
    before["sources"] = [
        {
            "path": "Study/Raw/Capture.md",
            "sha256": "old",
            "processed_at": "2026-01-01T00:00:00Z",
            "custom_source": "keep",
        }
    ]
    before["generated_files"] = [
        {
            "path": "Study/Notes/Linear systems.md",
            "custom_output": "keep",
            "user_note_sources": ["Study/Raw/Capture.md"],
        }
    ]
    log.write_text(json.dumps(before))
    service.refresh()
    c = Coordinator(service)
    ident = c.propose(plan_for(service))["id"]
    assert json.loads(log.read_text()) == before
    c.apply(ident, receipt_for(service, key, ident))
    after = json.loads(log.read_text())
    assert after["sources"][0]["processed_at"]
    assert "previous_processed_at" not in after["sources"][0]
    assert after["sources"][0]["custom_source"] == "keep"
    assert after["generated_files"][0]["custom_output"] == "keep"
    assert after["generated_files"][0]["user_note_sources"] == ["Study/Raw/Capture.md"]


def test_competing_save_after_final_check_is_preserved(env, monkeypatch):
    import os

    service, key, _ = env
    service.refresh()
    c = Coordinator(service)
    ident = c.propose(plan_for(service))["id"]
    log = service.config.vault / "Planning/Processing log.json"
    original = json.loads(log.read_text())
    competing = json.dumps({**original, "concurrent_owner_edit": True})
    rename = os.rename

    def race(src, dst, **kwargs):
        if src == "Processing log.json":
            log.write_text(competing)
        return rename(src, dst, **kwargs)

    monkeypatch.setattr(os, "rename", race)
    with pytest.raises(VaultError, match="Competing edit"):
        c.apply(ident, receipt_for(service, key, ident))
    assert log.read_text() == competing
    assert not json.loads(log.read_text())["sources"]
    assert (
        service.db.execute("SELECT state FROM proposals WHERE id=?", (ident,)).fetchone()[0]
        == "applying"
    )


def test_save_during_missing_path_window_is_not_overwritten(env, monkeypatch):
    import os

    from vault_retrieval.writes import recovery_dir

    service, key, _ = env
    service.refresh()
    c = Coordinator(service)
    ident = c.propose(plan_for(service))["id"]
    body = json.loads(
        service.db.execute("SELECT body FROM proposals WHERE id=?", (ident,)).fetchone()[0]
    )
    log = service.config.vault / "Planning/Processing log.json"
    original = log.read_bytes()
    link = os.link

    def race(src, dst, **kwargs):
        if src == "staged" and dst == "Processing log.json":
            log.write_text('{"sources": [], "owner_edit": true}')
        return link(src, dst, **kwargs)

    monkeypatch.setattr(os, "link", race)
    with pytest.raises(VaultError, match="Destination appeared"):
        c.apply(ident, receipt_for(service, key, ident))
    assert json.loads(log.read_text())["owner_edit"]
    assert (recovery_dir(service.config, body["actions"][-1]) / "captured").read_bytes() == original


def test_crash_after_capture_can_resume_without_losing_original(env, monkeypatch):
    import os

    service, key, _ = env
    service.refresh()
    c = Coordinator(service)
    ident = c.propose(plan_for(service))["id"]
    receipt = receipt_for(service, key, ident)
    rename = os.rename

    def crash(src, dst, **kwargs):
        rename(src, dst, **kwargs)
        raise RuntimeError("simulated process exit after capture")

    monkeypatch.setattr(os, "rename", crash)
    with pytest.raises(RuntimeError, match="simulated"):
        c.apply(ident, receipt)
    monkeypatch.setattr(os, "rename", rename)
    assert c.apply(ident, receipt)["state"] == "completed"
    assert c.run_intake()["pending"] == []


def test_crash_after_publication_link_recovers(env, monkeypatch):
    import os

    service, key, _ = env
    service.refresh()
    c = Coordinator(service)
    ident = c.propose(plan_for(service))["id"]
    receipt = receipt_for(service, key, ident)
    link = os.link

    def crash(src, dst, **kwargs):
        link(src, dst, **kwargs)
        raise RuntimeError("exit after publication link")

    monkeypatch.setattr(os, "link", crash)
    with pytest.raises(RuntimeError, match="publication link"):
        c.apply(ident, receipt)
    monkeypatch.setattr(os, "link", link)
    assert c.apply(ident, receipt)["state"] == "completed"


def test_invalid_registry_fails_without_modification(env):
    from vault_retrieval.registry import Registry

    service, _, _ = env
    log = service.config.vault / "Planning/Processing log.json"
    for value in [
        {"schema_version": 2, "sources": []},
        {"sources": [{"path": "a"}, {"path": "a"}]},
        {"sources": [{"path": "a", "outputs": "not a list"}]},
        {"sources": [], "generated_files": [None]},
    ]:
        original = json.dumps(value)
        log.write_text(original)
        with pytest.raises(VaultError):
            Registry(service.config)
        assert log.read_text() == original
