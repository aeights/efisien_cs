from app.rag.embeddings import Embedder
from app.rag.store import ChromaStore


class Retriever:
    def __init__(self, store: ChromaStore, embedder: Embedder) -> None:
        self.store = store
        self.embedder = embedder

    def search(self, query: str, k: int = 4) -> list[dict]:
        if self.store.count() == 0:
            return []
        vector = self.embedder.embed_query(query)
        return self.store.query(vector, k=k)
