"""Audit trail: every step is written to local JSONL (always) and Azure Cosmos DB (when configured)."""
import uuid
from datetime import datetime, timezone

from .config import dumps


class Audit:
    def __init__(self, settings):
        self.path = settings.out_dir / "audit.jsonl"
        self.container = None
        self.cosmos_error = None
        if settings.cosmos_endpoint and settings.cosmos_key:
            try:
                from azure.cosmos import CosmosClient
                c = CosmosClient(settings.cosmos_endpoint, settings.cosmos_key)
                self.container = c.get_database_client(settings.cosmos_db).get_container_client(
                    settings.cosmos_container)
            except Exception as e:
                self.cosmos_error = str(e)

    def log(self, case_id, step, agent, payload=None):
        doc = dict(id=str(uuid.uuid4()), case_id=case_id, ts=datetime.now(timezone.utc).isoformat(),
                   step=step, agent=agent, payload=payload or {})
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(dumps(doc) + "\n")
        if self.container is not None:
            try:
                import json
                self.container.upsert_item(json.loads(dumps(doc)))
            except Exception as e:
                self.cosmos_error = str(e)
        return doc
