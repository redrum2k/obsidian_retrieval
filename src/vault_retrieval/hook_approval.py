"""Durable approval from an explicitly configured, verified host event contract."""

import json
import re

from .common import VaultError, canonical, digest, now
from .hook_host import verify_host

COMMAND = re.compile(r"IMPLEMENT ([0-9a-f]{64})")


def command_id(event):
    prompt = event.get("prompt")
    if event.get("hook_event_name") != "UserPromptSubmit" or not isinstance(prompt, str):
        return None
    match = COMMAND.fullmatch(prompt.strip())
    return match[1] if match else None


def record_event(service, event):
    ident = command_id(event)
    if ident is None:
        return None
    config = service.config
    settings = config.data.get("hook_approval", {})
    if config.data.get("approval_scheme") != "codex-hook" or settings.get("enabled") is not True:
        raise VaultError(
            "hook_disabled", "Conversation approval is not enabled; no batch was approved."
        )
    if event.get("session_id") != settings.get("session_id") or not settings.get("session_id"):
        return None
    verify_host(settings)
    # The verified host marks child submissions; root submissions omit these fields.
    if (
        "agent_id" in event
        or "agent_type" in event
        or event.get("is_subagent")
        or event.get("is_automation")
    ):
        raise VaultError(
            "unverified_origin", "Subagent or automation events cannot approve a batch."
        )
    session, turn = event["session_id"], event.get("turn_id")
    if not isinstance(turn, str) or not turn or len(turn) > 200:
        raise VaultError("invalid_event", "A host turn ID is required.")
    event_id = digest(canonical([session, turn]).encode())
    with service.store.lock():
        service.check_policy()
        row = service.db.execute("SELECT * FROM proposals WHERE id=?", (ident,)).fetchone()
        if not row or row["state"] not in {"pending", "applying", "completed"}:
            raise VaultError("conflict", "Proposal is unknown or superseded; no approval recorded.")
        body = json.loads(row["body"])
        body_hash = digest(canonical(body).encode())
        if body["config"] != config.revision:
            raise VaultError("conflict", "Configuration changed; review a new proposal.")
        delivery = service.db.execute(
            "SELECT * FROM proposal_deliveries WHERE proposal_id=? AND session_id=?",
            (ident, session),
        ).fetchone()
        if (
            not delivery
            or delivery["body_digest"] != body_hash
            or delivery["config_revision"] != config.revision
        ):
            raise VaultError(
                "not_delivered", "The exact proposal has no delivery record in this conversation."
            )
        prior = service.db.execute(
            "SELECT * FROM hook_approvals WHERE event_id=?", (event_id,)
        ).fetchone()
        if prior and (prior["proposal_id"] != ident or prior["body_digest"] != body_hash):
            raise VaultError(
                "replayed_event", "This host turn already authorized a different proposal."
            )
        # No extraction or generation here. Apply repeats all source/target checks.
        if row["state"] == "pending":
            for source in body["sources"]:
                if digest(config.read(source["path"])) != source["revision"]:
                    raise VaultError("conflict", "Source changed; review a new proposal.")
            for action in body["actions"]:
                path = config.check(action["path"], write=True)
                actual = digest(config.read(action["path"])) if path.exists() else None
                if actual != action["expected_hash"]:
                    raise VaultError("conflict", "Target changed; review a new proposal.")
        with service.db:
            service.db.execute(
                "INSERT OR IGNORE INTO hook_approvals VALUES (?,?,?,?,?,?,?)",
                (event_id, session, turn, ident, body_hash, config.revision, now()),
            )
    return {
        "proposal_id": ident,
        "event_id": event_id,
        "state": row["state"],
        "approval_recorded": True,
    }


def verify_event(config, db, body, receipt):
    settings = config.data.get("hook_approval", {})
    verify_host(settings)
    row = (
        db.execute(
            "SELECT * FROM hook_approvals WHERE event_id=?", (receipt.get("hook_event_id"),)
        ).fetchone()
        if db is not None
        else None
    )
    if (
        settings.get("enabled") is not True
        or not row
        or row["proposal_id"] != body["id"]
        or row["body_digest"] != digest(canonical(body).encode())
        or row["config_revision"] != config.revision
        or row["session_id"] != settings.get("session_id")
    ):
        raise VaultError(
            "approval_required", "A recorded host approval for this exact batch is required."
        )


def recorded_receipt(service, proposal_id):
    row = service.db.execute(
        "SELECT event_id FROM hook_approvals WHERE proposal_id=? ORDER BY created LIMIT 1",
        (proposal_id,),
    ).fetchone()
    if not row:
        raise VaultError("approval_required", "No hook approval exists for this proposal.")
    return {"hook_event_id": row["event_id"]}
