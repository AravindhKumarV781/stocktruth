#!/usr/bin/env python3
"""Create the Azure AI Search index and upload knowledge/*.md (SOPs, contracts, policy).
WHEN : RUNBOOK Step 6, after 00_check_env.py shows AI Search PASS. Run again after editing anything in knowledge/.
WHERE: Azure Cloud Shell, from the project folder.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stocktruth.config import Settings  # noqa: E402

if __name__ == "__main__":
    s = Settings()
    if not (s.search_endpoint and s.search_key):
        sys.exit("Set SEARCH_ENDPOINT and SEARCH_KEY (admin key) in .env first.")
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import SearchableField, SearchFieldDataType, SearchIndex, SimpleField

    cred = AzureKeyCredential(s.search_key)
    index = SearchIndex(name=s.search_index, fields=[
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SearchableField(name="content", type=SearchFieldDataType.String)])
    SearchIndexClient(s.search_endpoint, cred).create_or_update_index(index)
    docs = []
    for p in sorted(s.knowledge_dir.glob("*.md")):
        txt = p.read_text(encoding="utf-8")
        docs.append(dict(id=p.stem.replace(".", "-"), title=txt.splitlines()[0].lstrip("# ").strip(), content=txt))
    res = SearchClient(s.search_endpoint, s.search_index, cred).upload_documents(docs)
    print(f"Indexed {sum(1 for r in res if r.succeeded)}/{len(docs)} documents into '{s.search_index}'")
