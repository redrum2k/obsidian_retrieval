import json
import os

import pytest

from vault_retrieval.common import VaultError, canonical
from vault_retrieval.config import Config
from vault_retrieval.output import ENCODING, page
from vault_retrieval.service import Service


def test_incremental_cache_restart_and_stale(env):
    service, _, data = env
    assert service.refresh()["extracted"] == 1
    items = service.search("Gaussian")
    assert items and items[0]["locator"]["line_start"] == 1
    assert service.refresh()["extracted"] == 0
    other = Service(Config(data))
    assert other.refresh(full=True)["extracted"] == 0
    other.store.close()
    path = service.config.vault / "Study/Raw/Capture.md"
    old = path.stat()
    path.write_text(path.read_text().replace("Gaussian", "Laplace!"))
    os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
    assert service.search("Gaussian") == []
    assert service.read_sections([items[0]["id"]])[0]["error"] == "stale_revision"
    service.refresh(full=True)
    assert service.search("Laplace")


def test_exclusions_code_symlinks_and_hardlinks(env):
    service, _, _ = env
    vault = service.config.vault
    (vault / "Study/Private").mkdir()
    (vault / "Study/Private/secret.md").write_text("unique_secret")
    (vault / "Study/Raw/alias.md").symlink_to(vault / "Study/Private/secret.md")
    (vault / "Study/code").mkdir()
    (vault / "Study/code/README.md").write_text("unique_code")
    (vault / "Study/project").mkdir()
    (vault / "Study/project/pyproject.toml").write_text("")
    (vault / "Study/project/doc.md").write_text("unique_project")
    service.refresh()
    assert len(service.config.inventory()) == 1
    assert not service.search("unique_secret unique_code unique_project")
    os.link(vault / "Study/Private/secret.md", vault / "Study/Raw/hard.md")
    with pytest.raises(VaultError):
        service.config.read("Study/Raw/hard.md")


def test_cs_exception_and_future_roots(env):
    service, _, data = env
    vault = service.config.vault
    course = vault / "Spring_2027/CS999"
    (course / "documents").mkdir(parents=True)
    (course / "src").mkdir()
    (course / "pyproject.toml").write_text("")
    (course / "documents/lecture.md").write_text("study lecture")
    (course / "README.md").write_text("infrastructure")
    (course / "src/secret.md").write_text("code documentation")
    data.update(discover_future_cs=True, cs_study_exception=True)
    config = Config(data)
    assert "Spring_2027/CS999/documents/lecture.md" in config.inventory()
    assert not any("README" in p or "/src/" in p for p in config.inventory())


def test_context_only_registry_and_generated(env):
    service, _, _ = env
    vault = service.config.vault
    name = "Study/documents/Reading.md"
    (vault / name).write_text("forbidden_context_evidence")
    registry = {
        "sources": [{"path": name, "status": "context_only", "note_creation_allowed": False}],
        "generated_files": [{"path": "Study/Raw/Capture.md"}],
    }
    (vault / "Planning/Processing log.json").write_text(json.dumps(registry))
    service.refresh()
    assert not service.search("forbidden_context_evidence")
    assert not list(service.db.execute("SELECT * FROM work WHERE state='pending'"))


def test_rename_delete_and_rebuild(env):
    service, _, _ = env
    service.refresh()
    ident = service.search("Gaussian")[0]["document_id"]
    vault = service.config.vault
    (vault / "Study/Raw/Capture.md").rename(vault / "Study/Raw/Renamed.md")
    service.refresh(full=True)
    assert service.search("Gaussian")[0]["document_id"] == ident
    assert service.changes()[-1]["reason"] == "renamed"
    service.refresh(rebuild=True)
    assert service.search("Gaussian")[0]["document_id"] == ident
    (vault / "Study/Raw/Renamed.md").unlink()
    service.refresh()
    assert not service.search("Gaussian")
    assert service.changes()[-1]["reason"] == "deleted_or_excluded"


def test_budget_unicode_and_continuations():
    original = "你好 Gaussian 🦆 " * 500
    items = [{"id": "a", "text": original, "locator": {"page": 1}}, {"id": "b", "text": "last"}]
    result, texts, token = None, [], None
    for _ in range(100):
        result = page(items, {"generation": "1"}, {"command": "read"}, 300, 1, token)
        assert result["output_tokens"] == len(
            ENCODING.encode(canonical(result) + "\n", disallowed_special=())
        )
        assert result["output_tokens"] <= 300
        texts.extend(x["text"] for x in result["items"] if x["id"] == "a")
        token = result["continuation"]
        if not token:
            break
    assert "".join(texts) == original
    first = page(items, {}, {}, 300, 1)
    with pytest.raises(VaultError, match="snapshot"):
        page(items, {"changed": True}, {}, 300, 1, first["continuation"])


def test_exclusion_revocation_purges_cache_and_direct_read(env):
    service, _, data = env
    service.refresh()
    item = service.search("Gaussian")[0]
    data["exclude"].append("Study/Raw")
    other = Service(Config(data))
    assert other.read_sections([item["id"]])[0]["error"] == "excluded"
    other.refresh()
    assert not other.search("Gaussian")
    assert not list(other.extractor.cache.iterdir())
    other.store.close()


def test_read_only_and_alias_rank(env):
    service, _, _ = env
    vault = service.config.vault
    (vault / "Study/Raw/Alias.md").write_text(
        "---\naliases: [Quokka]\n---\n# Animals\nA marsupial.\n"
    )
    (vault / "Study/Raw/Body.md").write_text("# Other\nQuokka here.\n")
    before = {str(p): p.read_bytes() for p in vault.rglob("*") if p.is_file()}
    service.refresh()
    assert service.search("Quokka")[0]["path"] == "Study/Raw/Alias.md"
    service.refresh(rebuild=True)
    after = {str(p): p.read_bytes() for p in vault.rglob("*") if p.is_file()}
    assert before == after


def test_empty_glossary_becomes_pending_after_edit(env):
    service, _, data = env
    data["glossary"] = ["Study/Raw/Capture.md"]
    source = service.config.vault / "Study/Raw/Capture.md"
    source.write_text("# Paste glossary here\n")
    service.refresh()
    assert service.db.execute("SELECT state FROM work").fetchone()[0] == "awaiting_content"
    source.write_text("# Paste glossary here\nA new mathematical definition.\n")
    service.refresh()
    assert service.db.execute("SELECT count(*) FROM work WHERE state='pending'").fetchone()[0] == 1


def test_corrupt_extraction_does_not_complete_or_hide_other_inputs(env):
    service, _, _ = env
    (service.config.vault / "Study/documents/Broken.docx").write_bytes(b"not a zip")
    result = service.refresh()
    assert result["failed"] == 1
    assert service.search("Gaussian")
    assert (
        service.db.execute(
            "SELECT status FROM documents WHERE path LIKE '%Broken.docx'"
        ).fetchone()[0]
        == "failed"
    )
    assert (
        service.db.execute("SELECT count(*) FROM work WHERE state='completed'").fetchone()[0] == 0
    )
    assert service.refresh()["failed"] == 1


def test_context_revocation_withholds_old_index_immediately(env):
    service, _, _ = env
    service.refresh()
    item = service.search("Gaussian")[0]
    path = service.config.vault / "Planning/Processing log.json"
    path.write_text(
        json.dumps({"sources": [{"path": "Study/Raw/Capture.md", "status": "context_only"}]})
    )
    assert service.read_sections([item["id"]])[0]["error"] == "context_only"
    service.refresh()
    assert not service.search("Gaussian")


def test_live_grounding_mode_discovers_without_extracting_unknown_readings(env):
    service, _, data = env
    data["require_grounding_for_index"] = True
    (service.config.vault / "Study/documents/Unstudied.md").write_text(
        "# Unstudied\nDo not index this reading.\n"
    )
    other = Service(Config(data))
    other.refresh()
    assert not other.search("Unstudied")
    row = other.db.execute("SELECT * FROM documents WHERE path LIKE '%Unstudied.md'").fetchone()
    assert row["status"] == "awaiting_grounding" and row["cache_key"] is None
    other.store.close()


def test_indexed_backlinks_and_rename_reports_without_repair(env):
    service, _, _ = env
    note = service.config.vault / "Study/Notes/Reference.md"
    note.write_text("# Reference\n[[Study/Raw/Capture.md]]\n")
    service.refresh()
    ident = service.search("Gaussian")[0]["document_id"]
    links = service.neighbors(ident, "backlinks")
    assert links[0]["path"] == "Study/Notes/Reference.md"
    (service.config.vault / "Study/Raw/Capture.md").rename(
        service.config.vault / "Study/Raw/Renamed.md"
    )
    service.refresh()
    assert any(e["reason"] == "dependent_link_needs_review" for e in service.changes())
    assert "[[Study/Raw/Capture.md]]" in note.read_text()


def test_new_configured_inputs_are_admitted_without_authorship_permission(env):
    from conftest import plan_for

    from vault_retrieval.coordinator import Coordinator

    service, _, data = env
    data["require_grounding_for_index"] = True
    data["user_note_paths"] = []
    service.refresh(full=True)
    assert service.db.execute("SELECT state FROM work").fetchone()[0] == "blocked"
    data["input_rules"] = [{"pattern": "Study/Raw/*", "formats": [".md"]}]
    admitted = Service(Config(data))
    try:
        admitted.refresh()
        assert admitted.search("Gaussian")
        assert admitted.db.execute("SELECT state FROM work").fetchone()[0] == "pending"
        with pytest.raises(VaultError, match="provenance"):
            Coordinator(admitted).propose(plan_for(admitted))
        path = admitted.config.vault / "Study/Raw/Tomorrow.md"
        path.write_text("# Next capture\nEigenvectors from today.\n")
        admitted.refresh()
        assert admitted.search("Eigenvectors")
        assert admitted.refresh()["extracted"] == 0
        data["input_rules"] = []
        with pytest.raises(VaultError, match="admission"):
            admitted.current(
                admitted.db.execute(
                    "SELECT * FROM documents WHERE path=?", ("Study/Raw/Tomorrow.md",)
                ).fetchone()
            )
    finally:
        admitted.store.close()


def test_input_rules_keep_context_exclusions_and_format_boundaries(env):
    service, _, data = env
    data["require_grounding_for_index"] = True
    data["input_rules"] = [{"pattern": "Study/documents/*", "formats": [".md"]}]
    vault = service.config.vault
    for name in ["New", "Context", "contract"]:
        (vault / f"Study/documents/{name}.md").write_text(
            f"# {name}\nDistinctive {name} content.\n"
        )
    (vault / "Study/documents/Other.pdf").write_bytes(b"not admitted for extraction")
    (vault / data["processing_log"]).write_text(
        json.dumps({"sources": [{"path": "Study/documents/Context.md", "status": "context_only"}]})
    )
    service.refresh(full=True)
    rows = {r["path"]: r["status"] for r in service.db.execute("SELECT * FROM documents")}
    assert rows["Study/documents/New.md"] == "ready"
    assert rows["Study/documents/Context.md"] == "context_only"
    assert rows["Study/documents/Other.pdf"] == "awaiting_grounding"
    assert "Study/documents/contract.md" not in rows
