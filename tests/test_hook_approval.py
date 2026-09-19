import copy
import json

import pytest
from conftest import plan_for

from vault_retrieval.common import VaultError
from vault_retrieval.config import Config
from vault_retrieval.coordinator import Coordinator
from vault_retrieval.hook import probe
from vault_retrieval.hook_approval import command_id, record_event, recorded_receipt
from vault_retrieval.hook_host import HOST_CONTRACT
from vault_retrieval.service import Service


@pytest.fixture
def hooked(env, tmp_path, monkeypatch):
    import hashlib

    host = tmp_path / "host"
    host.write_bytes(b"isolated verified build fixture")
    monkeypatch.setattr(
        "vault_retrieval.hook_host.HOST_FILES",
        {str(host): hashlib.sha256(host.read_bytes()).hexdigest()},
    )
    _, _, data = env
    data = copy.deepcopy(data)
    data["approval_scheme"] = "codex-hook"
    data["hook_approval"] = {
        "enabled": True,
        "session_id": "owner-session",
        "host_contract": HOST_CONTRACT,
    }
    service = Service(Config(data))
    service.refresh()
    c = Coordinator(service)
    ident = c.propose(plan_for(service))["id"]
    c.acknowledge(ident, "owner-session")
    event = {
        "hook_event_name": "UserPromptSubmit",
        "prompt": "IMPLEMENT " + ident,
        "session_id": "owner-session",
        "turn_id": "turn-1",
    }
    yield service, c, ident, event
    service.store.close()


def test_hook_apply_once_and_quiet(hooked):
    service, c, ident, event = hooked
    first = record_event(service, event)
    assert record_event(service, event) == first
    assert not (service.config.vault / "Study/Notes/Linear systems.md").exists()
    receipt = recorded_receipt(service, ident)
    assert c.apply(ident, receipt)["state"] == "completed"
    assert c.apply(ident, receipt)["already_applied"]
    assert c.run_intake()["quiet"] and not c.pending()
    assert service.db.execute("SELECT count(*) FROM hook_approvals").fetchone()[0] == 1


@pytest.mark.parametrize(
    "patch",
    [
        {"prompt": '"IMPLEMENT ID"'},
        {"prompt": "Please IMPLEMENT ID"},
        {"prompt": "IMPLEMENT"},
        {"hook_event_name": "Stop"},
        {"session_id": "other"},
    ],
)
def test_irrelevant_messages_do_not_approve(hooked, patch):
    service, _, _, event = hooked
    event.update(patch)
    assert record_event(service, event) is None
    assert service.db.execute("SELECT count(*) FROM hook_approvals").fetchone()[0] == 0


@pytest.mark.parametrize(
    "patch",
    [
        {"agent_id": None},
        {"agent_type": "worker"},
        {"is_automation": True},
        {"agent_id": "child"},
        {"turn_id": ""},
    ],
)
def test_invalid_provenance_blocks(hooked, patch):
    service, _, _, event = hooked
    event.update(patch)
    with pytest.raises(VaultError):
        record_event(service, event)
    assert service.db.execute("SELECT count(*) FROM hook_approvals").fetchone()[0] == 0


def test_missing_delivery_and_forged_receipt_fail(hooked):
    service, c, ident, event = hooked
    with pytest.raises(VaultError):
        c.apply(ident, {"approved": True})
    with pytest.raises(VaultError):
        c.acknowledge(ident, "other")
    with service.db:
        service.db.execute("DELETE FROM proposal_deliveries")
    with pytest.raises(VaultError, match="delivery"):
        record_event(service, event)


def test_changed_files_and_recovery(hooked):
    service, c, ident, event = hooked
    record_event(service, event)
    receipt = recorded_receipt(service, ident)
    with pytest.raises(VaultError, match="Injected"):
        c.apply(ident, receipt, fail_after=1)
    other = Service(service.config)
    try:
        assert (
            Coordinator(other).apply(ident, recorded_receipt(other, ident))["state"] == "completed"
        )
    finally:
        other.store.close()


def test_conflicting_source_after_approval_fails(hooked):
    service, c, ident, event = hooked
    record_event(service, event)
    (service.config.vault / "Study/Raw/Capture.md").write_text("concurrent edit")
    with pytest.raises(VaultError, match="Source"):
        c.apply(ident, recorded_receipt(service, ident))
    assert not (service.config.vault / "Study/Notes/Linear systems.md").exists()


def test_probe_never_saves_message(tmp_path):
    event = {
        "prompt": "private note text",
        "session_id": "sample",
        "hook_event_name": "UserPromptSubmit",
    }
    assert probe(event, tmp_path) is None
    text = next(tmp_path.glob("*.json")).read_text()
    assert "private note text" not in text
    assert json.loads(text)["session_id"] == "sample"
    assert (
        command_id(
            {"hook_event_name": "UserPromptSubmit", "prompt": " IMPLEMENT " + "a" * 64 + "\n"}
        )
        == "a" * 64
    )


def test_mutated_body_and_config_invalidate_approval(hooked):
    service, c, ident, event = hooked
    record_event(service, event)
    receipt = recorded_receipt(service, ident)
    service.config.revision = "changed"
    with pytest.raises(VaultError, match="approval"):
        c.apply(ident, receipt)


def test_hook_entrypoint_returns_apply_instruction_without_writes(hooked):
    import time

    from vault_retrieval.hook import handle

    service, _, ident, event = hooked
    config_path = service.config.state / "test-config.json"
    config_path.write_text(json.dumps(service.config.data))
    started = time.perf_counter()
    result = handle(event, config_path)
    elapsed = time.perf_counter() - started
    assert elapsed < 2
    instruction = result["hookSpecificOutput"]["additionalContext"]
    assert "apply-hook --id " + ident in instruction
    assert not (service.config.vault / "Study/Notes/Linear systems.md").exists()
    assert "approval_recorded" not in instruction  # status is plain explanatory text


def test_host_upgrade_blocks_recording_and_apply(hooked):
    from vault_retrieval.hook_host import HOST_FILES

    service, c, ident, event = hooked
    record_event(service, event)
    receipt = recorded_receipt(service, ident)
    from pathlib import Path

    Path(next(iter(HOST_FILES))).write_bytes(b"new unverified host")
    with pytest.raises(VaultError, match="Desktop build changed"):
        record_event(service, {**event, "turn_id": "turn-2"})
    with pytest.raises(VaultError, match="Desktop build changed"):
        c.apply(ident, receipt)
    assert not (service.config.vault / "Study/Notes/Linear systems.md").exists()


def test_fictional_origin_flag_does_not_enable_contract(hooked):
    service, _, _, event = hooked
    service.config.data["hook_approval"].pop("host_contract")
    service.config.data["hook_approval"]["host_contract_verified"] = True
    with pytest.raises(VaultError, match="verified desktop hook contract"):
        record_event(service, event)


def test_production_probe_never_records_or_applies(hooked):
    from vault_retrieval.hook import handle

    service, _, _, event = hooked
    config_path = service.config.state / "test-config.json"
    config_path.write_text(json.dumps(service.config.data))
    result = handle({**event, "prompt": "VAULT_HOOK_PROBE"}, config_path)
    assert "approved nothing" in result["hookSpecificOutput"]["additionalContext"]
    receipt = json.loads((service.config.state / "hook-probe-status.json").read_text())
    assert receipt["status"] == "ready"
    assert receipt["turn_id"] == event["turn_id"]
    assert receipt["approval_recorded"] is False
    assert "prompt" not in receipt
    assert service.db.execute("SELECT count(*) FROM hook_approvals").fetchone()[0] == 0


def test_heartbeat_tool_result_and_wrapped_command_are_not_approval(hooked):
    service, _, ident, event = hooked
    assert (
        record_event(
            service,
            {
                "input": [],
                "toolOutput": {
                    "name": "automation_update",
                    "namespace": "codex_app",
                    "output": "IMPLEMENT " + ident,
                },
            },
        )
        is None
    )
    assert (
        record_event(service, {**event, "prompt": "<heartbeat>IMPLEMENT " + ident + "</heartbeat>"})
        is None
    )
    assert service.db.execute("SELECT count(*) FROM hook_approvals").fetchone()[0] == 0


def test_stdin_hook_handoff_applies_reviewed_batch(hooked, monkeypatch, capsys):
    import io
    import shlex
    import sys

    from vault_retrieval import cli, hook

    service, c, ident, event = hooked
    config_path = service.config.state / "test-config.json"
    config_path.write_text(json.dumps(service.config.data))
    monkeypatch.setattr(sys, "argv", ["hook", "--config", str(config_path)])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
    assert hook.main() == 0
    instruction = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
    assert not (service.config.vault / "Study/Notes/Linear systems.md").exists()
    command = instruction.split("CLI now: ", 1)[1].split(". Report", 1)[0]
    args = shlex.split(command)
    assert args[1:3] == ["-m", "vault_retrieval.cli"]
    monkeypatch.setattr(sys, "argv", ["vault", *args[3:]])
    assert cli.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["items"][0]["state"] == "completed"
    assert (service.config.vault / "Study/Notes/Linear systems.md").exists()
    assert c.run_intake()["quiet"] and not c.pending()


@pytest.mark.parametrize(
    "prompt",
    [
        "VAULT_HOOK_PROBE\n",
        "`VAULT_HOOK_PROBE`\n",
        r"VAULT\_HOOK\_PROBE",
        r"VAULT\\_HOOK\\_PROBE",
    ],
)
def test_chat_formatted_probe_is_diagnostic_only(hooked, prompt):
    from vault_retrieval.hook import handle

    service, _, _, event = hooked
    config_path = service.config.state / "test-config.json"
    config_path.write_text(json.dumps(service.config.data))
    assert handle({**event, "prompt": prompt}, config_path)
    receipt = json.loads((service.config.state / "hook-probe-status.json").read_text())
    assert receipt["status"] == "ready"
    assert service.db.execute("SELECT count(*) FROM hook_approvals").fetchone()[0] == 0
    assert not (service.config.vault / "Study/Notes/Linear systems.md").exists()
    assert command_id({**event, "prompt": "`" + event["prompt"] + "`"}) is None


def test_probe_does_not_accept_prose_or_other_events():
    from vault_retrieval.hook import is_probe

    assert not is_probe({"hook_event_name": "Stop", "prompt": "VAULT_HOOK_PROBE"})
    assert not is_probe(
        {"hook_event_name": "UserPromptSubmit", "prompt": "Please VAULT_HOOK_PROBE"}
    )
