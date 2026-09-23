import json

import pytest

from vault_retrieval.common import VaultError
from vault_retrieval.config import Config
from vault_retrieval.coordinator import Coordinator
from vault_retrieval.extract import Extractor
from vault_retrieval.service import Service


def test_intake_never_constructs_extractor_and_returns_changed_inputs(env, monkeypatch):
    service, _, _ = env
    (service.config.vault / "Study/documents/Scan.pdf").write_bytes(b"not yet extracted")

    def forbidden(*args, **kwargs):
        pytest.fail("Intake initialized converters/extraction")

    monkeypatch.setattr(Extractor, "__init__", forbidden)
    first = Coordinator(service).run_intake()
    assert first["refresh"]["extracted"] == 0
    assert len(first["pending"]) == 2
    assert {r["status"] for r in first["pending"]} == {"needs_extraction"}
    assert first["pending"][0]["source_role"] == "raw"
    again = Coordinator(service).run_intake()
    assert again["refresh"]["changed"] == 0
    assert again["pending"] == first["pending"]


def test_selected_extraction_and_restart_preserve_pending_and_cache(env, monkeypatch):
    service, _, data = env
    (service.config.vault / "Study/documents/Scan.pdf").write_bytes(b"corrupt PDF")
    first = Coordinator(service).run_intake()
    capture = first["pending"][0]["document_id"]
    report = service.extract_documents([capture])
    assert report["extracted"] == 1
    assert report["failed"] == 0
    assert service.search("Gaussian")
    assert "partial_coverage" in service.warnings
    before = service.db.execute("SELECT id FROM sections").fetchall()
    assert service.refresh(full=True, extraction_paths=set())["extracted"] == 0
    assert service.db.execute("SELECT id FROM sections").fetchall() == before
    other = Service(Config(data))
    try:
        pending = Coordinator(other).run_intake()["pending"]
        assert len(pending) == 2
        assert other.extract_documents([capture])["extracted"] == 0
        scan = next(r for r in pending if r["path"].endswith(".pdf"))
        assert other.extract_documents([scan["document_id"]])["failed"] == 1
        failed = Coordinator(other).run_intake()["pending"]
        assert any(r["status"] == "failed" for r in failed)
        source = other.config.vault / "Study/Raw/Capture.md"
        source.write_text("# Changed\nNew evidence\n")
        Coordinator(other).run_intake()
        assert not other.search("Gaussian")
    finally:
        other.store.close()


def test_discovery_respects_registry_revocation(env):
    service, _, _ = env
    service.refresh()
    log = service.config.vault / "Planning/Processing log.json"
    log.write_text(
        json.dumps({"sources": [{"path": "Study/Raw/Capture.md", "status": "context_only"}]})
    )
    Coordinator(service).run_intake()
    assert not service.search("Gaussian")
    assert Coordinator(service).pending() == []
    with pytest.raises(VaultError):
        service.extract_documents(["missing"])


def test_config_change_preserves_unchanged_extraction(env, monkeypatch):
    service, _, data = env
    service.refresh()
    before = [tuple(r) for r in service.db.execute("SELECT * FROM sections")]
    data["roots"][0]["project"] = "renamed project"
    other = Service(Config(data))
    try:

        def forbidden(*args, **kwargs):
            pytest.fail("Discovery must reuse extraction without constructing an extractor")

        monkeypatch.setattr(Extractor, "__init__", forbidden)
        pending = Coordinator(other).run_intake()["pending"]
        assert pending[0]["status"] == "ready"
        assert [tuple(r) for r in other.db.execute("SELECT * FROM sections")] == before
        assert other.db.execute("SELECT project FROM documents").fetchone()[0] == "renamed project"
    finally:
        other.store.close()


def test_reverted_source_revision_returns_to_pending(env):
    service, _, _ = env
    path = service.config.vault / "Study/Raw/Capture.md"
    original = path.read_text()
    coordinator = Coordinator(service)
    first = coordinator.run_intake()["pending"][0]
    path.write_text("# Temporary revision\nChanged content\n")
    coordinator.run_intake()
    path.write_text(original)
    pending = coordinator.run_intake()["pending"]
    assert len(pending) == 1
    assert pending[0]["revision"] == first["revision"]
