import copy
import json

import pytest
from conftest import plan_for, receipt_for

from vault_retrieval.common import VaultError
from vault_retrieval.config import Config
from vault_retrieval.coordinator import Coordinator
from vault_retrieval.registry import Registry
from vault_retrieval.service import Service


@pytest.fixture
def inventory(env):
    base, key, data = env
    data = copy.deepcopy(data)
    data["user_note_paths"] = []
    data["resource_inventory_permissions"] = {
        "onboarding": {
            "instruction": "Organize the attributed email and resource links; do not summarize papers.",
            "sources": ["Study/Raw/Capture.md"],
            "outputs": ["Study/Notes/Inventory.md"],
        }
    }
    (base.config.vault / "Study/Raw/Capture.md").write_text(
        "# Email\nSender: Read the linked paper.\n"
    )
    service = Service(Config(data))
    service.refresh()
    plan = plan_for(service)
    plan.update(purpose="resource_inventory", authorization_id="onboarding")
    plan["sources"][0]["outputs"] = ["Study/Notes/Inventory.md"]
    plan["changes"][0].update(
        path="Study/Notes/Inventory.md",
        content="---\nstatus: draft\n---\nSource: [[Study/Raw/Capture.md]]\nSender recommends reading.\n",
    )
    yield service, key, data, plan
    service.store.close()


def test_inventory_approval_completion_and_later_study(inventory):
    service, key, data, plan = inventory
    c = Coordinator(service)
    original = service.config.read("Study/Raw/Capture.md")
    proposal = c.propose(plan)
    ident = proposal["id"]
    assert c.propose(plan)["id"] == ident
    body = json.loads(
        service.db.execute("SELECT body FROM proposals WHERE id=?", (ident,)).fetchone()[0]
    )
    assert body["purpose"] == "resource_inventory"
    assert body["authorization"] == data["resource_inventory_permissions"]["onboarding"]
    assert not body["sources"][0]["grounding"]["confirmed_user_note"]
    assert "Scoped authorization" in open(proposal["review_file"]).read()
    with pytest.raises(VaultError):
        c.apply(ident, {"approved": True})
    assert not (service.config.vault / "Study/Notes/Inventory.md").exists()
    receipt = receipt_for(service, key, ident)
    with pytest.raises(VaultError, match="Injected"):
        c.apply(ident, receipt, fail_after=1)
    assert c.apply(ident, receipt)["state"] == "completed"
    assert c.apply(ident, receipt)["already_applied"]
    assert service.config.read("Study/Raw/Capture.md") == original
    registry = Registry(service.config)
    doc = body["sources"][0]
    assert registry.completed(doc["path"], doc["revision"], "resource_inventory")
    assert not registry.completed(doc["path"], doc["revision"])
    assert registry.data["sources"] == []
    assert registry.data["inventory_sources"][0]["user_note_sources"] == []
    assert len(c.pending()) == 1  # Study eligibility is independent of inventory completion.
    with pytest.raises(VaultError, match="already recorded"):
        c.propose(plan)
    study = plan_for(service)
    with pytest.raises(VaultError, match="provenance"):
        c.propose(study)
    study["sources"][0]["grounding"] = {
        "user_authored_evidence": "New verified owner provenance for this test."
    }
    study_id = c.propose(study)["id"]
    c.apply(study_id, receipt_for(service, key, study_id))
    registry = Registry(service.config)
    assert registry.completed(doc["path"], doc["revision"])
    assert registry.completed(doc["path"], doc["revision"], "resource_inventory")


@pytest.mark.parametrize(
    "mutation", ["missing_permission", "unknown_purpose", "study", "output", "source"]
)
def test_inventory_scope_rejections(inventory, mutation):
    service, _, _, plan = inventory
    if mutation == "missing_permission":
        plan["authorization_id"] = "not-authorized"
    elif mutation == "unknown_purpose":
        plan["purpose"] = "anything"
    elif mutation == "study":
        plan.pop("purpose")
    elif mutation == "output":
        plan["changes"][0]["path"] = "Study/Notes/Other.md"
    else:
        path = service.config.vault / "Study/Raw/Other.md"
        path.write_text("# Another email\nUnrelated material\n")
        service.refresh()
        doc = service.db.execute(
            "SELECT id,hash FROM documents WHERE path='Study/Raw/Other.md'"
        ).fetchone()
        plan["sources"][0].update(id=doc["id"], revision=doc["hash"])
    with pytest.raises(VaultError):
        Coordinator(service).propose(plan)
    assert service.db.execute("SELECT count(*) FROM proposals").fetchone()[0] == 0


def test_revoked_inventory_authorization_rejects_old_approval(inventory):
    service, key, data, plan = inventory
    ident = Coordinator(service).propose(plan)["id"]
    receipt = receipt_for(service, key, ident)
    data["resource_inventory_permissions"] = {}
    other = Service(Config(data))
    try:
        with pytest.raises(VaultError):
            Coordinator(other).apply(ident, receipt)
        assert not (service.config.vault / "Study/Notes/Inventory.md").exists()
    finally:
        other.store.close()


@pytest.mark.parametrize(
    "field,value", [("sources", ["Study/Raw/*"]), ("outputs", []), ("instruction", "")]
)
def test_invalid_inventory_permission_rejected(inventory, field, value):
    _, _, data, _ = inventory
    data["resource_inventory_permissions"]["onboarding"][field] = value
    with pytest.raises(VaultError):
        Config(data)
