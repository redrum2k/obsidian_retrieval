import base64
import difflib
import json
import os
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .common import VaultError, canonical, digest, now
from .registry import Registry


def next_trigger(after):
    local = after.astimezone(ZoneInfo("America/New_York"))
    for day in range(8):
        candidate = (local + timedelta(days=day)).replace(
            hour=12, minute=10, second=0, microsecond=0
        )
        if candidate.weekday() in {0, 2, 4, 6} and candidate > local:
            return candidate.isoformat()


class Coordinator:
    def __init__(self, service):
        self.service = service
        self.config, self.store, self.db = service.config, service.store, service.db

    def pending(self):
        rows = self.db.execute("""SELECT d.*,w.state,w.proposal_id FROM work w
            JOIN documents d ON d.id=w.document_id AND d.hash=w.revision
            WHERE d.active=1 AND d.status IN ('ready','awaiting_grounding') AND w.state IN ('pending','blocked') AND w.proposal_id IS NULL
            ORDER BY CASE WHEN d.role IN ('raw','glossary') THEN 0 ELSE 1 END,d.path""")
        return [
            {
                "document_id": r["id"],
                "path": r["path"],
                "revision": r["hash"],
                "source_role": r["role"],
                "status": r["status"],
                "warnings": json.loads(r["warnings"]),
            }
            for r in rows
        ]

    def run_intake(self, plan=None):
        with self.store.lock():
            refresh = self.service.refresh(locked=True)
            self.supersede()
            proposal = self.propose(plan, locked=True) if plan else None
            # Existing host delivers these artifacts in the current conversation and ACKs them.
            notifications = [
                {
                    "proposal_id": r["id"],
                    "review_file": str(self.config.state / "proposals" / (r["id"] + ".md")),
                    "delivery_key": r["id"],
                }
                for r in self.db.execute(
                    "SELECT id FROM proposals WHERE state='pending' AND delivery<>'confirmed'"
                )
            ]
            pending = self.pending()
            return {
                "refresh": refresh,
                "proposal_id": proposal["id"] if proposal else None,
                "notifications": notifications,
                "pending": pending,
                "quiet": not notifications,
                "needs_planning": bool(pending),
                "next_trigger": next_trigger(datetime.now(ZoneInfo("America/New_York"))),
            }

    def supersede(self):
        with self.db:
            for row in self.db.execute(
                "SELECT * FROM proposals WHERE state IN ('pending','approved')"
            ).fetchall():
                body = json.loads(row["body"])
                invalid = body["config"] != self.config.revision
                for action in body["actions"]:
                    try:
                        path = self.config.check(action["path"], write=True)
                        current = (
                            digest(self.config.read(action["path"])) if path.exists() else None
                        )
                        if current != action["expected_hash"]:
                            invalid = True
                    except (OSError, VaultError):
                        invalid = True
                for source in body["sources"]:
                    doc = self.db.execute(
                        "SELECT * FROM documents WHERE id=? AND active=1", (source["id"],)
                    ).fetchone()
                    if not doc or doc["hash"] != source["revision"]:
                        invalid = True
                if invalid:
                    self.db.execute(
                        "UPDATE proposals SET state='superseded' WHERE id=?", (row["id"],)
                    )
                    self.db.execute(
                        "UPDATE work SET state='pending',proposal_id=NULL WHERE proposal_id=? AND state<>'completed'",
                        (row["id"],),
                    )

    def propose(self, plan, locked=False):
        if not locked:
            with self.store.lock():
                return self.propose(plan, True)
        self.service.check_policy()
        registry = Registry(self.config)
        self.supersede()
        sources, actions = [], []
        if not plan or not plan.get("sources") or not plan.get("changes"):
            raise VaultError(
                "invalid_plan", "A proposal needs source IDs/revisions and concrete changes."
            )
        if len(plan["sources"]) > 20 or len(plan["changes"]) > 20:
            raise VaultError("invalid_plan", "A batch supports at most 20 sources and 20 changes.")
        for source in plan["sources"]:
            doc = self.db.execute(
                "SELECT * FROM documents WHERE id=? AND active=1", (source["id"],)
            ).fetchone()
            if not doc or source["revision"] != doc["hash"]:
                raise VaultError("stale_revision", "Refresh the proposal source list.")
            self.service.current(doc)
            if doc["role"] in {"generated", "scaffold"} or doc["status"] != "ready":
                raise VaultError(
                    "ungrounded", "Generated, scaffold, or failed sources cannot initiate work."
                )
            if registry.completed(doc["path"], doc["hash"]):
                raise VaultError(
                    "already_processed", "This revision is already recorded as processed."
                )
            grounding = source.get("grounding", {})
            explicit = self.config.data.get("integration_permissions", {}).get(doc["path"])
            known_user = doc["path"] in self.config.data.get("user_note_paths", [])
            related = grounding.get("user_note_sources", [])
            if (
                not explicit
                and not known_user
                and not related
                and not grounding.get("user_authored_evidence")
            ):
                raise VaultError(
                    "ungrounded",
                    "Supply directly related user-note provenance or a configured named-source permission.",
                )
            for name in related:
                if name not in self.config.data.get("user_note_paths", []):
                    raise VaultError(
                        "ungrounded",
                        "User-note provenance must be confirmed in owner configuration.",
                    )
                self.config.read(name)
            if related and not grounding.get("topic_relation"):
                raise VaultError(
                    "ungrounded", "Explain the direct topic relationship for approval review."
                )
            warnings = json.loads(doc["warnings"])
            if warnings and not source.get("visual_review", {}).get("coverage"):
                raise VaultError(
                    "visual_review_required",
                    "Supply reviewed page/slide coverage and uncertainties.",
                )
            if "render_unavailable" in warnings or "ocr_unavailable" in warnings:
                raise VaultError(
                    "visual_review_required",
                    "Install the missing local extraction/render dependency before processing.",
                )
            sources.append(
                {
                    "id": doc["id"],
                    "path": doc["path"],
                    "revision": doc["hash"],
                    "grounding": {
                        **grounding,
                        "confirmed_user_note": known_user
                        or bool(grounding.get("user_authored_evidence")),
                        "named_permission": explicit,
                    },
                    "visual_review": source.get("visual_review"),
                    "outputs": source.get("outputs", []),
                }
            )
        paths = set()
        for change in plan["changes"]:
            name, text = change["path"], change["content"]
            if name == self.config.data["processing_log"] or name in paths:
                raise VaultError(
                    "invalid_plan",
                    "Duplicate paths and manual registry replacement are not permitted.",
                )
            path = self.config.check(name, write=True)
            if name in {s["path"] for s in sources}:
                raise VaultError("excluded", "Original inputs must be preserved.")
            if not isinstance(text, str) or not text.strip():
                raise VaultError("invalid_plan", "Empty concept scaffolds are not permitted.")
            if "Raw" in Path(name).parts and "derived_companion: true" not in text:
                raise VaultError(
                    "invalid_plan", "Raw companions must declare 'derived_companion: true'."
                )
            if "status: draft" not in text:
                raise VaultError("invalid_plan", "Derived notes must declare 'status: draft'.")
            linked = [s for s in sources if name in s["outputs"]]
            if not linked or any(s["path"] not in text for s in linked):
                raise VaultError(
                    "ungrounded", "Every output needs a source mapping and visible source path."
                )
            if "Raw" in Path(name).parts and path.exists() and name not in registry.generated:
                raise VaultError("excluded", "Existing original Raw captures cannot be replaced.")
            before = self.config.read(name) if path.exists() else None
            if change.get("expected_hash") != (digest(before) if before is not None else None):
                raise VaultError("conflict", "Target changed since the plan was prepared.")
            actions.append(
                {
                    "path": name,
                    "before": before.decode() if before is not None else None,
                    "expected_hash": change.get("expected_hash"),
                    "content": text,
                    "output_hash": digest(text.encode()),
                }
            )
            paths.add(name)
        if any(not s["outputs"] or not set(s["outputs"]).issubset(paths) for s in sources):
            raise VaultError(
                "invalid_plan", "Every source must map to changed outputs in this batch."
            )
        self.validate_links(actions)
        # Identity binds the exact registry baseline and configuration, but not wall-clock time.
        batch_id = digest(
            canonical(
                {
                    "sources": sources,
                    "actions": actions,
                    "registry": registry.hash,
                    "config": self.config.revision,
                    "external_sources": plan.get("external_sources", []),
                    "uncertainties": plan.get("uncertainties", []),
                }
            ).encode()
        )
        existing = self.db.execute("SELECT * FROM proposals WHERE id=?", (batch_id,)).fetchone()
        if existing:
            return {"id": batch_id, "state": existing["state"]}
        for source in sources:
            reserved = self.db.execute(
                "SELECT proposal_id FROM work WHERE document_id=? AND revision=?",
                (source["id"], source["revision"]),
            ).fetchone()
            if reserved and reserved[0]:
                raise VaultError(
                    "pending_proposal", "An unchanged proposal already covers this source revision."
                )
        records = registry.data
        for source in sources:
            old = next((s for s in records.get("sources", []) if s["path"] == source["path"]), {})
            record = {
                **old,
                "path": source["path"],
                "sha256": source["revision"],
                "status": "processed",
                "prepared_at": now(),
                "outputs": source["outputs"],
                "output_hashes": {
                    a["path"]: a["output_hash"] for a in actions if a["path"] in source["outputs"]
                },
                "user_note_sources": source["grounding"].get("user_note_sources")
                or ([source["path"]] if source["grounding"]["confirmed_user_note"] else []),
                "coverage": plan.get("coverage", "Approved proposal; see batch record"),
                "proposal_id": batch_id,
            }
            if "processed_at" in record:
                record["previous_processed_at"] = record.pop("processed_at")
            records["sources"] = [
                s for s in records.get("sources", []) if s["path"] != source["path"]
            ] + [record]
        records["generated_files"] = [
            g for g in records.get("generated_files", []) if g["path"] not in paths
        ] + [
            {"path": a["path"], "sha256": a["output_hash"], "last_updated_at": now()}
            for a in actions
        ]
        records.setdefault("completed_batches", []).append(
            {"proposal_id": batch_id, "status": "completed", "outputs": sorted(paths)}
        )
        log_text = json.dumps(records, ensure_ascii=False, indent=2) + "\n"
        actions.append(
            {
                "path": self.config.data["processing_log"],
                "before": registry.raw.decode() if registry.raw else None,
                "expected_hash": registry.hash,
                "content": log_text,
                "output_hash": digest(log_text.encode()),
            }
        )
        body = {
            "id": batch_id,
            "config": self.config.revision,
            "sources": sources,
            "actions": actions,
            "uncertainties": plan.get("uncertainties", []),
            "external_sources": plan.get("external_sources", []),
        }
        folder = self.config.state / "proposals"
        folder.mkdir(exist_ok=True)
        review = (
            f"# Processing proposal {batch_id}\n\nNo vault changes until explicit approval.\n\n"
        )
        review += (
            "## Sources and grounding\n\n```json\n"
            + json.dumps(sources, ensure_ascii=False, indent=2)
            + "\n```\n"
        )
        review += (
            "\nUncertainties: "
            + canonical(body["uncertainties"])
            + "\nExternal sources: "
            + canonical(body["external_sources"])
            + "\n"
        )
        for action in actions:
            diff = "".join(
                difflib.unified_diff(
                    (action["before"] or "").splitlines(True),
                    action["content"].splitlines(True),
                    fromfile=action["path"],
                    tofile=action["path"],
                )
            )
            review += "\n```diff\n" + diff + "\n```\n"
        (folder / (batch_id + ".md")).write_text(review)
        (folder / (batch_id + ".json")).write_text(canonical(body))
        with self.db:
            self.db.execute(
                "INSERT INTO proposals(id,body,state,created) VALUES (?,?,'pending',?)",
                (batch_id, canonical(body), now()),
            )
            for source in sources:
                self.db.execute(
                    "INSERT OR REPLACE INTO work VALUES (?,?,'proposed',?)",
                    (source["id"], source["revision"], batch_id),
                )
        return {
            "id": batch_id,
            "state": "pending",
            "approval_digest": digest(canonical(body).encode()),
            "review_file": str(folder / (batch_id + ".md")),
        }

    def validate_links(self, actions):
        planned = {a["path"] for a in actions}
        for action in actions:
            for target in re.findall(r"\[\[([^\]|#]+)", action["content"]):
                candidates = [
                    target,
                    target + ".md",
                    str(Path(action["path"]).parent / target),
                    str(Path(action["path"]).parent / (target + ".md")),
                ]
                valid = False
                for name in candidates:
                    try:
                        path = self.config.check(name)
                        if name in planned or path.exists():
                            valid = True
                    except VaultError:
                        continue
                if not valid:
                    raise VaultError(
                        "broken_link", "A proposed wiki link has no eligible unambiguous target."
                    )

    def acknowledge(self, proposal_id):
        with self.db:
            result = self.db.execute(
                "UPDATE proposals SET delivery='confirmed' WHERE id=? AND state='pending'",
                (proposal_id,),
            )
        if not result.rowcount:
            raise VaultError("not_found", "No pending proposal to acknowledge.")
        return {"id": proposal_id, "delivery": "confirmed"}

    def verify_approval(self, body, receipt):
        key = self.config.data.get("approval_public_key")
        expected = {
            "proposal_id": body["id"],
            "proposal_digest": digest(canonical(body).encode()),
            "decision": "approve",
        }
        if not key or receipt.get("message") != expected:
            raise VaultError(
                "approval_required",
                "A trusted approval receipt bound to this exact proposal is required.",
            )
        try:
            Ed25519PublicKey.from_public_bytes(base64.b64decode(key)).verify(
                base64.b64decode(receipt["signature"]), canonical(expected).encode()
            )
        except (InvalidSignature, ValueError, KeyError) as exc:
            raise VaultError("approval_required", "Approval receipt signature is invalid.") from exc

    def apply(self, proposal_id, receipt, fail_after=None):
        with self.store.lock():
            self.service.check_policy()
            row = self.db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
            if not row:
                raise VaultError("not_found", "Proposal does not exist.")
            body = json.loads(row["body"])
            self.verify_approval(body, receipt)
            if row["state"] == "completed":
                return {"id": proposal_id, "state": "completed", "already_applied": True}
            if row["state"] == "superseded" or body["config"] != self.config.revision:
                raise VaultError(
                    "conflict", "Proposal or configuration changed; create a new proposal."
                )
            for source in body["sources"]:
                if digest(self.config.read(source["path"])) != source["revision"]:
                    raise VaultError("conflict", "Source revision changed after review.")
            actions = body["actions"]
            self.validate_links(actions[:-1])
            # All preconditions checked before first mutation; recovery checks durable intent.
            for i, action in enumerate(actions):
                path = self.config.check(action["path"], write=True)
                actual = digest(self.config.read(action["path"])) if path.exists() else None
                intent = self.db.execute(
                    "SELECT state FROM actions WHERE proposal_id=? AND ordinal=?", (proposal_id, i)
                ).fetchone()
                if actual != action["expected_hash"] and not (
                    intent and actual == action["output_hash"]
                ):
                    raise VaultError(
                        "conflict", "A target differs from its approved or already-applied content."
                    )
            with self.db:
                self.db.execute(
                    "UPDATE proposals SET state='applying',signature=? WHERE id=?",
                    (canonical(receipt), proposal_id),
                )
            backups = self.config.state / "backups" / proposal_id
            backups.mkdir(parents=True, exist_ok=True)
            for i, action in enumerate(actions):
                path = self.config.check(action["path"], write=True)
                actual = digest(self.config.read(action["path"])) if path.exists() else None
                intent = self.db.execute(
                    "SELECT state FROM actions WHERE proposal_id=? AND ordinal=?", (proposal_id, i)
                ).fetchone()
                if intent and actual == action["output_hash"]:
                    continue
                if actual != action["expected_hash"]:
                    raise VaultError("conflict", "Target changed during application.")
                if action["before"] is not None:
                    backup = backups / str(i)
                    if not backup.exists():
                        with backup.open("xb") as f:
                            f.write(action["before"].encode())
                            f.flush()
                            os.fsync(f.fileno())
                with self.db:
                    self.db.execute(
                        "INSERT OR REPLACE INTO actions VALUES (?,?,'intent')", (proposal_id, i)
                    )
                self.write_action(action)
                with self.db:
                    self.db.execute(
                        "UPDATE actions SET state='done' WHERE proposal_id=? AND ordinal=?",
                        (proposal_id, i),
                    )
                if fail_after is not None and i + 1 == fail_after:
                    raise VaultError(
                        "interrupted",
                        "Injected crash after a durable action; retry the same approval.",
                    )
            for action in actions:
                if digest(self.config.read(action["path"])) != action["output_hash"]:
                    raise VaultError(
                        "conflict", "Post-write verification failed; operation remains incomplete."
                    )
            with self.db:
                self.db.execute("UPDATE proposals SET state='completed' WHERE id=?", (proposal_id,))
                self.db.execute(
                    "UPDATE work SET state='completed' WHERE proposal_id=?", (proposal_id,)
                )
            self.service.refresh(locked=True)
            return {
                "id": proposal_id,
                "state": "completed",
                "written": [a["path"] for a in actions],
            }

    def write_action(self, action):
        # Parent folders must already be designated/created by the owner; no broad mkdir traversal.
        parent, leaf = self.config.open_parent(action["path"], write=True, create=True)
        temp = ".vault-stage-" + uuid.uuid4().hex
        try:
            fd = os.open(
                temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent
            )
            with os.fdopen(fd, "wb") as f:
                f.write(action["content"].encode())
                f.flush()
                os.fsync(f.fileno())
            if action["expected_hash"] is None:
                # link() atomically refuses a destination that appeared after preflight.
                os.link(temp, leaf, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
            else:
                if digest(self.config.read(action["path"])) != action["expected_hash"]:
                    raise VaultError("conflict", "Target changed immediately before replacement.")
                os.replace(temp, leaf, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            try:
                os.unlink(temp, dir_fd=parent)
            except FileNotFoundError:
                pass
            os.close(parent)
