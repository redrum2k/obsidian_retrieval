import base64
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from vault_retrieval.common import canonical, digest
from vault_retrieval.config import Config
from vault_retrieval.service import Service


@pytest.fixture
def env(tmp_path):
    vault = tmp_path / "vault"
    for folder in ["Study/Raw", "Study/Notes", "Study/documents", "Planning"]:
        (vault / folder).mkdir(parents=True)
    (vault / "Study/Raw/Capture.md").write_text(
        "# Linear systems\nMy notes explain Gaussian elimination and row operations.\n"
    )
    (vault / "Planning/Processing log.json").write_text(
        json.dumps(
            {"schema_version": 1, "sources": [], "generated_files": [], "custom": "preserve me"}
        )
    )
    key = Ed25519PrivateKey.generate()
    data = {
        "enabled": True,
        "vault": str(vault),
        "state": str(tmp_path / "state"),
        "roots": [{"path": "Study", "role": "study", "project": "sample"}],
        "exclude": ["Study/Private"],
        "outputs": ["Study/Notes"],
        "processing_log": "Planning/Processing log.json",
        "operational_files": ["AGENTS.md"],
        "user_note_paths": ["Study/Raw/Capture.md"],
        "approval_public_key": base64.b64encode(
            key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        ).decode(),
    }
    service = Service(Config(data))
    yield service, key, data
    service.store.close()


def plan_for(service):
    doc = service.db.execute("SELECT * FROM documents WHERE path='Study/Raw/Capture.md'").fetchone()
    content = "---\nstatus: draft\n---\n# Linear systems\n\nSource: [[Study/Raw/Capture.md]]\n\nGaussian elimination and row operations.\n"
    return {
        "sources": [
            {"id": doc["id"], "revision": doc["hash"], "outputs": ["Study/Notes/Linear systems.md"]}
        ],
        "changes": [
            {"path": "Study/Notes/Linear systems.md", "expected_hash": None, "content": content}
        ],
    }


def receipt_for(service, key, ident):
    body = json.loads(
        service.db.execute("SELECT body FROM proposals WHERE id=?", (ident,)).fetchone()[0]
    )
    message = {
        "proposal_id": ident,
        "proposal_digest": digest(canonical(body).encode()),
        "decision": "approve",
    }
    return {
        "message": message,
        "signature": base64.b64encode(key.sign(canonical(message).encode())).decode(),
    }
