"""Knowledge base: Azure AI Search when configured, local keyword search otherwise."""
import re
from pathlib import Path


def _tokens(s):
    return set(w for w in re.findall(r"[a-z0-9_]+", s.lower()) if len(w) > 2)


class LocalKB:
    engine = "local_keyword"

    def __init__(self, folder):
        self.docs = []
        for p in sorted(Path(folder).glob("*.md")):
            txt = p.read_text(encoding="utf-8")
            self.docs.append(dict(id=p.stem, title=txt.splitlines()[0].lstrip("# ").strip(), content=txt))

    def search(self, query, k=3):
        q = _tokens(query)
        scored = []
        for d in self.docs:
            score = len(q & _tokens(d["content"])) + 2 * len(q & _tokens(d["title"]))
            if score:
                scored.append((score, d))
        scored.sort(key=lambda x: -x[0])
        return [dict(doc_id=d["id"], title=d["title"], snippet=d["content"][:700]) for _, d in scored[:k]]


class KB:
    def __init__(self, settings):
        self.local = LocalKB(settings.knowledge_dir)
        self.engine = self.local.engine
        self.client = None
        self.last_error = None
        if settings.search_endpoint and settings.search_key:
            try:
                from azure.core.credentials import AzureKeyCredential
                from azure.search.documents import SearchClient
                self.client = SearchClient(settings.search_endpoint, settings.search_index,
                                           AzureKeyCredential(settings.search_key))
                self.engine = "azure_ai_search"
            except Exception as e:
                self.last_error = str(e)

    def search(self, query, k=3):
        if self.client is not None:
            try:
                res = self.client.search(search_text=query, top=k)
                out = [dict(doc_id=r["id"], title=r["title"], snippet=r["content"][:700]) for r in res]
                if out:
                    return out
            except Exception as e:
                self.last_error = str(e)
                self.engine = "local_keyword (azure search failed)"
        return self.local.search(query, k)
