import json
import re
import shutil
import subprocess
import time
import uuid
import zipfile
from functools import cached_property
from pathlib import Path

import yaml
from lxml.etree import XMLSyntaxError

from .common import VaultError, canonical, digest, now
from .registry import Registry
from .store import Store


class Service:
    def __init__(self, config):
        self.config = config
        if config.data.get("enabled") is not True:
            raise VaultError(
                "disabled",
                "Configuration is a review draft; enable only after eligibility approval.",
            )
        self.check_policy()
        self.store = Store(config.state)
        self.db = self.store.db
        self.warnings = []

    @cached_property
    def extractor(self):
        from .extract import Extractor

        return Extractor(self.config.state, self.config.data.get("extraction"))

    def check_policy(self):
        policy = self.config.data.get("policy")
        if policy and digest(self.config.read(policy["path"])) != policy["sha256"]:
            raise VaultError(
                "policy_changed",
                "Read current vault policy and review configuration before continuing.",
            )

    def clear_sections(self, ident):
        self.db.execute(
            "DELETE FROM search_index WHERE section_id IN (SELECT id FROM sections WHERE document_id=?)",
            (ident,),
        )
        self.db.execute("DELETE FROM sections WHERE document_id=?", (ident,))
        self.db.execute("DELETE FROM links WHERE document_id=?", (ident,))

    def refresh(self, full=False, rebuild=False, locked=False, extraction_paths=None):
        """Reconcile inventory; None extracts all, a path set extracts only its members."""
        if not locked:
            with self.store.lock():
                return self.refresh(full, rebuild, True, extraction_paths)
        self.check_policy()
        start = time.monotonic()
        extractor_version = self.extractor.version if extraction_paths != set() else None
        registry = Registry(self.config)
        paths = self.config.inventory()
        previous = {
            r["path"]: dict(r) for r in self.db.execute("SELECT * FROM documents WHERE active=1")
        }
        missing = {p: r for p, r in previous.items() if p not in paths}
        counts = {
            "discovered": len(paths),
            "changed": 0,
            "extracted": 0,
            "cache_hits": 0,
            "failed": 0,
        }
        policy_changed = self.store.meta("config") != self.config.revision
        registry_hash = registry.hash or "absent"
        registry_changed = self.store.meta("registry") != registry_hash
        full = full or policy_changed or registry_changed or rebuild
        new_hashes = {p: digest(self.config.read(p)) for p in paths if p not in previous}
        with self.db:
            for path in paths:
                old = previous.get(path)
                info = self.config.check(path).stat()
                role, project = self.config.classify(path)
                if path in registry.generated:
                    role = "generated"
                extract = extraction_paths is None or path in extraction_paths
                if (
                    not full
                    and old
                    and old["size"] == info.st_size
                    and old["mtime"] == info.st_mtime_ns
                    and (not extract or old["status"] not in {"failed", "needs_extraction"})
                    and (not extract or old["extractor"] == extractor_version)
                ):
                    continue
                try:
                    data = self.config.read(path)
                    if path in new_hashes and digest(data) != new_hashes[path]:
                        raise VaultError(
                            "stale_revision", "New source changed during inventory; retry."
                        )
                except (OSError, VaultError):
                    # Do not retire a revision or claim a successful scan on access races.
                    raise VaultError(
                        "scan_failed", "An eligible input became unreadable; retry inventory."
                    )
                revision = digest(data)
                if not old:
                    candidates = [r for r in missing.values() if r["hash"] == revision]
                    # Only unambiguous disappearing-to-appearing pairs preserve identity.
                    if (
                        len(candidates) == 1
                        and sum(h == revision for h in new_hashes.values()) == 1
                    ):
                        old = candidates[0]
                        missing.pop(old["path"])
                ident = old["id"] if old else uuid.uuid4().hex
                reason = (
                    "created"
                    if not old
                    else "renamed"
                    if old["path"] != path
                    else "modified"
                    if old["hash"] != revision
                    else "role_changed"
                    if old["role"] != role
                    else None
                )
                context = registry.context_only(path) and path not in self.config.data.get(
                    "integration_permissions", {}
                )
                record = registry.record(path)
                unknown_grounding = self.needs_admission(path, role, record)
                admission_status = (
                    "context_only"
                    if context
                    else "awaiting_grounding"
                    if unknown_grounding
                    else "ready"
                )
                if (
                    old
                    and old["path"] == path
                    and old["hash"] == revision
                    and old["role"] == role
                    and not rebuild
                    and old["status"] == admission_status
                    and (not extract or old["extractor"] == extractor_version)
                ):
                    self.db.execute(
                        "UPDATE documents SET size=?,mtime=?,project=? WHERE id=?",
                        (len(data), info.st_mtime_ns, project, ident),
                    )
                    self.update_work(ident, path, revision, role, old["status"], registry)
                    continue
                result = {"metadata": {}, "warnings": [], "sections": []}
                key, status = None, admission_status
                if status == "ready" and not extract:
                    status = "needs_extraction"
                    if old and old["hash"] == revision:
                        key = old["cache_key"]
                if status == "ready":
                    try:
                        result, hit, key = self.extractor.extract(data, Path(path).suffix.lower())
                        counts["cache_hits" if hit else "extracted"] += 1
                    except (
                        VaultError,
                        ValueError,
                        UnicodeError,
                        RuntimeError,
                        OSError,
                        zipfile.BadZipFile,
                        subprocess.TimeoutExpired,
                        yaml.YAMLError,
                        XMLSyntaxError,
                    ) as exc:
                        status = "failed"
                        result["warnings"] = [getattr(exc, "code", "extraction_failed")]
                        counts["failed"] += 1
                self.clear_sections(ident)
                metadata = result["metadata"]
                title = str(metadata.get("title") or Path(path).stem)
                aliases = metadata.get("aliases") or []
                if not isinstance(aliases, (str, list)):
                    aliases = []
                aliases = aliases if isinstance(aliases, str) else " ".join(str(a) for a in aliases)
                self.db.execute(
                    """INSERT OR REPLACE INTO documents VALUES
                    (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                    (
                        ident,
                        path,
                        revision,
                        len(data),
                        info.st_mtime_ns,
                        role,
                        project,
                        title,
                        aliases,
                        str(metadata.get("author", "unknown")),
                        status,
                        canonical(result["warnings"]),
                        key,
                        extractor_version or (old["extractor"] if old else "unextracted"),
                    ),
                )
                if Path(path).suffix.lower() in {".md", ".markdown"} and status == "ready":
                    text = data.decode("utf-8")
                    targets = set(re.findall(r"\[\[([^\]|#]+)", text))
                    targets.update(re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", text))
                    for target in targets:
                        if "://" not in target:
                            self.db.execute(
                                "INSERT OR IGNORE INTO links VALUES (?,?,?)",
                                (ident, revision, target),
                            )
                if reason == "renamed":
                    self.report_broken_links(old["path"])
                for i, section in enumerate(result["sections"]):
                    sid = digest(f"{ident}:{revision}:{self.extractor.version}:{i}".encode())[:32]
                    self.db.execute(
                        "INSERT INTO sections VALUES (?,?,?,?,?,?,?)",
                        (
                            sid,
                            ident,
                            revision,
                            i,
                            section["heading"],
                            section["text"],
                            canonical(section["locator"]),
                        ),
                    )
                    self.db.execute(
                        "INSERT INTO search_index VALUES (?,?,?,?,?)",
                        (sid, title, aliases, section["heading"], section["text"]),
                    )
                if reason:
                    counts["changed"] += 1
                    self.db.execute(
                        "INSERT INTO events(document_id,path,project,revision,reason,observed) VALUES (?,?,?,?,?,?)",
                        (ident, path, project, revision, reason, now()),
                    )
                self.update_work(ident, path, revision, role, status, registry)
                self.db.execute(
                    "UPDATE work SET state='superseded' WHERE document_id=? AND revision<>? AND state<>'completed'",
                    (ident, revision),
                )
            for old in missing.values():
                self.report_broken_links(old["path"])
                self.clear_sections(old["id"])
                self.db.execute("UPDATE documents SET active=0 WHERE id=?", (old["id"],))
                self.db.execute(
                    "UPDATE work SET state='superseded' WHERE document_id=? AND state<>'completed'",
                    (old["id"],),
                )
                self.db.execute(
                    "INSERT INTO events(document_id,path,project,revision,reason,observed) VALUES (?,?,?,?,?,?)",
                    (
                        old["id"],
                        old["path"],
                        old["project"],
                        old["hash"],
                        "deleted_or_excluded",
                        now(),
                    ),
                )
                counts["changed"] += 1
            self.store.meta("generation", int(self.store.meta("generation")) + 1)
            self.store.meta("last_refresh", now())
            if full:
                self.store.meta("last_reconciliation", now())
            self.store.meta("config", self.config.revision)
            self.store.meta("registry", registry_hash)
            for metric in ("extracted", "cache_hits"):
                self.store.count(metric, counts[metric])
        referenced = {
            r[0] for r in self.db.execute("SELECT cache_key FROM documents WHERE active=1")
        }
        cache = self.config.state / "extractions"
        for folder in cache.iterdir() if cache.exists() else ():
            if folder.name not in referenced:
                shutil.rmtree(folder)
        return {
            **counts,
            "duration_ms": round((time.monotonic() - start) * 1000),
            "snapshot": self.snapshot(),
        }

    def update_work(self, ident, path, revision, role, status, registry):
        if role not in {"raw", "glossary", "study", "inbox"}:
            self.db.execute(
                "UPDATE work SET state='superseded' WHERE document_id=? AND state<>'completed'",
                (ident,),
            )
            return
        if registry.completed(path, revision):
            state = "completed"
        elif status == "needs_extraction":
            state = "pending"
        elif status != "ready":
            state = "blocked"
        else:
            text = self.db.execute("SELECT text FROM sections WHERE document_id=?", (ident,))
            has_content = any(re.sub(r"(?m)^#{1,6}.*$", "", row[0]).strip() for row in text)
            empty = (
                registry.record(path, revision).get("status") == "awaiting_content"
                or not has_content
            )
            state = "awaiting_content" if empty else "pending"
        self.db.execute("INSERT OR IGNORE INTO work VALUES (?,?,?,NULL)", (ident, revision, state))
        if state == "completed":
            self.db.execute(
                "UPDATE work SET state=? WHERE document_id=? AND revision=?",
                (state, ident, revision),
            )
        else:
            self.db.execute(
                "UPDATE work SET state=? WHERE document_id=? AND revision=? "
                "AND proposal_id IS NULL "
                "AND state IN ('blocked','pending','awaiting_content','superseded')",
                (state, ident, revision),
            )

    def extract_documents(self, ids):
        if not ids or len(ids) > 20:
            raise VaultError("invalid_input", "Select 1..20 document IDs for extraction.")
        paths = set()
        for ident in ids:
            doc = self.db.execute(
                "SELECT * FROM documents WHERE id=? AND active=1", (ident,)
            ).fetchone()
            if not doc:
                raise VaultError("not_found", "A selected document is missing; rerun intake.")
            self.config.check(doc["path"])
            paths.add(doc["path"])
        return self.refresh(extraction_paths=paths)

    def snapshot(self):
        return {
            "generation": self.store.meta("generation"),
            "config": self.config.revision,
            "last_refresh": self.store.meta("last_refresh"),
            "last_reconciliation": self.store.meta("last_reconciliation"),
        }

    def needs_admission(self, path, role, record):
        return self.config.data.get("require_grounding_for_index", False) and (
            role not in {"generated", "structured", "scaffold"}
            and not self.config.admitted_input(path)
            and path not in self.config.data.get("user_note_paths", [])
            and not record.get("user_note_sources")
            and path not in self.config.data.get("integration_permissions", {})
        )

    def current(self, doc):
        self.check_policy()
        if not doc or not doc["active"]:
            raise VaultError("deleted", "Document is no longer active.")
        if doc["extractor"] != self.extractor.version:
            raise VaultError(
                "stale_revision", "Extractor version changed; refresh before returning evidence."
            )
        registry = Registry(self.config)
        role = self.config.classify(doc["path"])[0]
        if self.needs_admission(doc["path"], role, registry.record(doc["path"])):
            raise VaultError("awaiting_grounding", "Input shape needs admission before retrieval.")
        data = self.config.read(doc["path"])
        if digest(data) != doc["hash"]:
            raise VaultError("stale_revision", "Refresh before reading changed evidence.")
        if registry.context_only(doc["path"]) and doc["path"] not in self.config.data.get(
            "integration_permissions", {}
        ):
            raise VaultError(
                "context_only", "This source is metadata-only under the processing registry."
            )
        return data

    def evidence(self, row, text=None):
        doc = self.db.execute(
            "SELECT * FROM documents WHERE id=?", (row["document_id"],)
        ).fetchone()
        self.current(doc)
        return {
            "id": row["id"],
            "document_id": doc["id"],
            "revision": doc["hash"],
            "path": doc["path"],
            "project": doc["project"],
            "source_role": doc["role"],
            "author": doc["author"],
            "heading": row["heading"],
            "locator": json.loads(row["locator"]),
            "warnings": json.loads(doc["warnings"]),
            "text": row["text"] if text is None else text,
            "excerpt_kind": "section_span" if text is None else "search_snippet",
        }

    def search(self, query, project=None, source_role=None):
        words = re.findall(r"\w+", query, re.UNICODE)
        if not words or len(query) > 2000:
            raise VaultError("invalid_input", "Supply a nonempty query of at most 2000 characters.")
        expression = " OR ".join('"' + w + '"' for w in words[:32])
        sql = """SELECT s.*, snippet(search_index,4,'','', ' … ',32) snippet
            FROM search_index JOIN sections s ON s.id=search_index.section_id
            JOIN documents d ON d.id=s.document_id WHERE search_index MATCH ? AND d.active=1"""
        args = [expression]
        for key, value in (("project", project), ("role", source_role)):
            if value:
                sql += f" AND d.{key}=?"
                args.append(value)
        sql += " ORDER BY bm25(search_index,0,8,6,3,1),s.id"
        items = []
        self.warnings = (
            ["partial_coverage"]
            if self.db.execute(
                "SELECT 1 FROM documents WHERE active=1 AND status<>'ready' LIMIT 1"
            ).fetchone()
            else []
        )
        for row in self.db.execute(sql, args):
            try:
                items.append(self.evidence(row, row["snippet"]))
            except (VaultError, OSError):
                self.warnings.append("stale_or_excluded_results_omitted")
                continue
        return items

    def read_sections(self, ids):
        items = []
        for ident in ids:
            row = self.db.execute("SELECT * FROM sections WHERE id=?", (ident,)).fetchone()
            try:
                if row is None:
                    raise VaultError("not_found", "Section no longer exists; search again.")
                items.append(self.evidence(row))
            except (VaultError, OSError) as exc:
                items.append({"id": ident, "error": getattr(exc, "code", "deleted")})
        return items

    def changes(self, since=0, project=None):
        try:
            since = int(since)
        except ValueError as exc:
            raise VaultError(
                "invalid_cursor", "Change checkpoint must be an integer sequence."
            ) from exc
        sql, args = "SELECT * FROM events WHERE seq>?", [since]
        if project:
            sql += " AND project=?"
            args.append(project)
        items = []
        for row in self.db.execute(sql + " ORDER BY seq", args):
            try:
                self.config.check(row["path"])
                items.append(dict(row))
            except VaultError:
                # Don't expose newly excluded paths from historical events.
                items.append({"seq": row["seq"], "reason": "excluded"})
        return items

    def processing_status(self, ids):
        registry = Registry(self.config)
        items = []
        for ident in ids:
            doc = self.db.execute("SELECT * FROM documents WHERE id=?", (ident,)).fetchone()
            if doc is None:
                items.append({"id": ident, "status": "unknown"})
                continue
            try:
                self.config.check(doc["path"])
            except VaultError:
                items.append({"id": ident, "status": "excluded"})
                continue
            record = registry.record(doc["path"], doc["hash"])
            work = self.db.execute(
                "SELECT state,proposal_id FROM work WHERE document_id=? AND revision=?",
                (ident, doc["hash"]),
            ).fetchone()
            items.append(
                {
                    "id": ident,
                    "revision": doc["hash"],
                    "status": record.get("status", "unknown"),
                    "extraction_status": doc["status"],
                    "warnings": json.loads(doc["warnings"]),
                    "context_only": registry.context_only(doc["path"]),
                    "user_note_sources": record.get("user_note_sources", []),
                    "outputs": record.get("outputs", []),
                    "work": dict(work) if work else None,
                }
            )
        return items

    def neighbors(self, ident, relation):
        row = self.db.execute("SELECT * FROM sections WHERE id=?", (ident,)).fetchone()
        doc = self.db.execute(
            "SELECT * FROM documents WHERE id=?", (row["document_id"] if row else ident,)
        ).fetchone()
        if doc is None:
            raise VaultError("not_found", "Unknown document or section.")
        self.current(doc)
        if relation == "adjacent":
            if row is None:
                raise VaultError("invalid_input", "Adjacent sections require a section ID.")
            return [
                self.evidence(s)
                for s in self.db.execute(
                    "SELECT * FROM sections WHERE document_id=? AND ordinal BETWEEN ? AND ? ORDER BY ordinal",
                    (doc["id"], row["ordinal"] - 1, row["ordinal"] + 1),
                )
            ]
        registry = Registry(self.config)
        targets = []
        if relation == "outputs":
            targets = registry.record(doc["path"]).get("outputs", [])
        elif relation == "sources":
            targets = [
                s["path"] for s in registry.sources.values() if doc["path"] in s.get("outputs", [])
            ]
        elif relation in {"links", "backlinks"}:
            if relation == "links":
                links = self.db.execute(
                    "SELECT * FROM links WHERE document_id=? AND revision=?",
                    (doc["id"], doc["hash"]),
                )
            else:
                links = self.db.execute(
                    "SELECT l.* FROM links l JOIN documents d ON d.id=l.document_id AND d.hash=l.revision WHERE d.active=1"
                )
            for link in links:
                source = self.db.execute(
                    "SELECT * FROM documents WHERE id=?", (link["document_id"],)
                ).fetchone()
                resolved = self.resolve_link(link["target"], source["path"])
                if relation == "links":
                    targets.append(resolved or link["target"])
                elif resolved == doc["path"]:
                    try:
                        self.current(source)
                        targets.append(source["path"])
                    except (OSError, VaultError):
                        self.warnings.append("stale_backlinks_omitted")
        else:
            raise VaultError(
                "invalid_input", "relation: adjacent, links, backlinks, sources, outputs"
            )
        items = []
        for target in sorted(set(targets)):
            try:
                self.config.check(target)
                other = self.db.execute(
                    "SELECT * FROM documents WHERE path=? AND active=1", (target,)
                ).fetchone()
                items.append(
                    {
                        "path": target,
                        "relation": relation,
                        "document_id": other["id"] if other else None,
                        "status": "resolved" if other else "unresolved",
                    }
                )
            except VaultError:
                continue
        return items

    def resolve_link(self, target, source_path):
        candidates = {
            target,
            target + ".md",
            str(Path(source_path).parent / target),
            str(Path(source_path).parent / (target + ".md")),
        }
        exact, names = [], []
        for row in self.db.execute("SELECT path FROM documents WHERE active=1"):
            try:
                self.config.check(row["path"])
            except VaultError:
                continue
            if row["path"] in candidates:
                exact.append(row["path"])
            elif Path(row["path"]).stem == target:
                names.append(row["path"])
        matches = exact or names
        return matches[0] if len(matches) == 1 else None

    def report_broken_links(self, old_path):
        candidates = {
            old_path,
            str(Path(old_path).with_suffix("")),
            Path(old_path).name,
            Path(old_path).stem,
        }
        for link in self.db.execute("SELECT DISTINCT document_id,target FROM links").fetchall():
            if link["target"] not in candidates:
                continue
            source = self.db.execute(
                "SELECT * FROM documents WHERE id=? AND active=1", (link["document_id"],)
            ).fetchone()
            if source:
                self.db.execute(
                    "INSERT INTO events(document_id,path,project,revision,reason,observed) VALUES (?,?,?,?,?,?)",
                    (
                        source["id"],
                        source["path"],
                        source["project"],
                        source["hash"],
                        "dependent_link_needs_review",
                        now(),
                    ),
                )

    def health(self):
        return {
            "snapshot": self.snapshot(),
            "documents": self.db.execute(
                "SELECT count(*) FROM documents WHERE active=1"
            ).fetchone()[0],
            "states": {
                r[0]: r[1]
                for r in self.db.execute("SELECT state,count(*) FROM work GROUP BY state")
            },
            "metrics": {r[0]: r[1] for r in self.db.execute("SELECT * FROM metrics")},
        }
