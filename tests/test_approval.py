import base64
import json

import pytest
from conftest import plan_for
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from vault_retrieval.approval import export_request
from vault_retrieval.common import VaultError, canonical, digest
from vault_retrieval.config import Config
from vault_retrieval.coordinator import Coordinator
from vault_retrieval.service import Service


def setup_p256(env):
    service, _, data = env
    key = ec.generate_private_key(ec.SECP256R1())
    data["approval_scheme"] = "p256-sha256"
    data["approval_public_key"] = base64.b64encode(
        key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
    ).decode()
    other = Service(Config(data))
    other.refresh()
    return other, key


def receipt(body, key):
    message = {
        "decision": "approve",
        "proposal_id": body["id"],
        "proposal_digest": digest(canonical(body).encode()),
    }
    return {
        "message": message,
        "signature": base64.b64encode(
            key.sign(canonical(message).encode(), ec.ECDSA(hashes.SHA256()))
        ).decode(),
    }


def test_p256_request_receipt_and_unchanged_run(env):
    service, key = setup_p256(env)
    try:
        c = Coordinator(service)
        proposal = c.propose(plan_for(service))
        exported = export_request(c, proposal["id"])
        from pathlib import Path

        payload = json.loads(Path(exported["request_file"]).read_text())
        body = json.loads(payload["canonical_body"])
        assert body["review_context"]["vault"] == str(service.config.vault)
        assert exported["proposal_digest"] == digest(payload["canonical_body"].encode())
        assert not (service.config.vault / "Study/Notes/Linear systems.md").exists()
        assert export_request(c, proposal["id"]) == exported
        signed = receipt(body, key)
        bad = receipt(body, ec.generate_private_key(ec.SECP256R1()))
        with pytest.raises(VaultError, match="signature"):
            c.apply(proposal["id"], bad)
        assert c.apply(proposal["id"], signed)["state"] == "completed"
        assert c.run_intake()["pending"] == []
        assert c.apply(proposal["id"], signed)["already_applied"]
    finally:
        service.store.close()


def test_stale_source_and_tampered_request_fail(env):
    service, key = setup_p256(env)
    try:
        c = Coordinator(service)
        ident = c.propose(plan_for(service))["id"]
        result = export_request(c, ident)
        from pathlib import Path

        path = Path(result["request_file"])
        original = path.read_text()
        path.write_text("{}")
        with pytest.raises(VaultError, match="differs"):
            export_request(c, ident)
        path.write_text(original)
        body = json.loads(json.loads(original)["canonical_body"])
        signed = receipt(body, key)
        signed["message"]["proposal_id"] = "0" * 64
        with pytest.raises(VaultError, match="receipt"):
            c.apply(ident, signed)
        (service.config.vault / "Study/Raw/Capture.md").write_text("Changed source")
        with pytest.raises(VaultError):
            export_request(c, ident)
    finally:
        service.store.close()
