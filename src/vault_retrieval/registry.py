import json

from .common import VaultError, digest


class Registry:
    """Preserves the owner's schema and unknown fields; never writes during discovery."""

    def __init__(self, config):
        self.config = config
        try:
            self.raw = config.read(config.data["processing_log"])
            self.data = json.loads(self.raw)
        except FileNotFoundError:
            self.raw = None
            self.data = {
                "schema_version": 1,
                "sources": [],
                "generated_files": [],
                "completed_batches": [],
            }
        if not isinstance(self.data, dict) or not isinstance(self.data.get("sources", []), list):
            raise VaultError(
                "invalid_registry",
                "Processing registry must use the configured JSON sources schema.",
            )
        if self.data.get("schema_version", 1) != 1:
            raise VaultError(
                "invalid_registry", "Unsupported registry schema; no migration is automatic."
            )
        for collection in ("sources", "generated_files", "inventory_sources"):
            rows = self.data.get(collection, [])
            if not isinstance(rows, list) or any(
                not isinstance(row, dict) or not isinstance(row.get("path"), str) for row in rows
            ):
                raise VaultError("invalid_registry", f"{collection} must contain path records.")
            if len({row["path"] for row in rows}) != len(rows):
                raise VaultError(
                    "invalid_registry", f"Duplicate paths in {collection}; review before writing."
                )
            for row in rows:
                for field in ("outputs", "user_note_sources"):
                    values = row.get(field, [])
                    if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                        raise VaultError("invalid_registry", f"{field} must be a list of paths.")
        for field in ("completed_batches", "workspace_setups"):
            values = self.data.get(field, [])
            if not isinstance(values, list) or any(not isinstance(v, dict) for v in values):
                raise VaultError("invalid_registry", f"{field} must be a list of records.")
        self.sources = {s["path"]: s for s in self.data.get("sources", [])}
        self.generated = {s["path"] for s in self.data.get("generated_files", [])}
        for source in [*self.sources.values(), *self.data.get("inventory_sources", [])]:
            self.generated.update(p for p in source.get("outputs", []) if p != source["path"])
        for setup in self.data.get("workspace_setups", []):
            if setup.get("scaffolding_not_study_evidence"):
                self.generated.update(setup.get("created_files", []))
        # Explicit glossary inputs can become actionable after placeholders change.
        self.generated.difference_update(config.data.get("glossary", []))

    def record(self, path, revision=None):
        result = self.sources.get(path, {})
        if revision is not None and result.get("sha256") != revision:
            return {}
        return result

    def context_only(self, path):
        s = self.record(path)
        return s.get("status") == "context_only" or s.get("note_creation_allowed") is False

    def completed(self, path, revision, purpose="study_notes"):
        if purpose == "resource_inventory":
            return any(
                row["path"] == path
                and row.get("sha256") == revision
                and row.get("status") == "processed"
                for row in self.data.get("inventory_sources", [])
            )
        s = self.record(path, revision)
        return (
            bool(s)
            and not self.context_only(path)
            and (s.get("status") in {"processed", "completed"} or bool(s.get("processed_at")))
        )

    @property
    def hash(self):
        return digest(self.raw) if self.raw is not None else None
