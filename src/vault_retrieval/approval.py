"""Export immutable review input; this module cannot issue approval receipts."""

import base64
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .common import VaultError, canonical, digest


def export_request(coordinator, proposal_id):
    service = coordinator.service
    with service.store.lock():
        service.check_policy()
        coordinator.supersede()
        row = service.db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        if not row or row["state"] != "pending":
            raise VaultError(
                "conflict", "Only a current pending proposal can be exported for approval."
            )
        body = json.loads(row["body"])
        if body.get("review_context") != {"vault": str(service.config.vault)}:
            raise VaultError(
                "invalid_proposal", "Regenerate this legacy proposal with a bound review context."
            )
        for source in body["sources"]:
            doc = service.db.execute(
                "SELECT * FROM documents WHERE id=?", (source["id"],)
            ).fetchone()
            service.current(doc)
        scheme = service.config.data.get("approval_scheme", "ed25519")
        public = service.config.data.get("approval_public_key")
        if scheme != "p256-sha256" or not public:
            raise VaultError(
                "approval_setup_required",
                "Enroll the macOS approval key and configure p256-sha256 before creating the final proposal.",
            )
        payload = {
            "version": 1,
            "canonical_body": canonical(body),
            "approval_public_key": public,
            "approval_scheme": scheme,
        }
        folder = service.config.state / "approval-requests"
        folder.mkdir(exist_ok=True)
        path = folder / (proposal_id + ".json")
        content = canonical(payload)
        if path.exists():
            if path.read_text() != content:
                raise VaultError(
                    "conflict", "Existing approval request differs; do not overwrite it."
                )
        else:
            with path.open("x") as handle:
                handle.write(content)
        return {
            "proposal_id": proposal_id,
            "proposal_digest": digest(canonical(body).encode()),
            "request_file": str(path),
            "approval_required": True,
        }


def verify_receipt(config, body, receipt, db=None):
    if config.data.get("approval_scheme") == "codex-hook":
        from .hook_approval import verify_event

        verify_event(config, db, body, receipt)
        return
    key = config.data.get("approval_public_key")
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
        scheme = config.data.get("approval_scheme", "ed25519")
        signature = base64.b64decode(receipt["signature"], validate=True)
        raw_key = base64.b64decode(key, validate=True)
        message = canonical(expected).encode()
        if scheme == "ed25519":
            Ed25519PublicKey.from_public_bytes(raw_key).verify(signature, message)
        elif scheme == "p256-sha256":
            ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw_key).verify(
                signature, message, ec.ECDSA(hashes.SHA256())
            )
        else:
            raise VaultError("approval_required", "Unsupported configured approval scheme.")
    except (InvalidSignature, ValueError, KeyError) as exc:
        raise VaultError("approval_required", "Approval receipt signature is invalid.") from exc
