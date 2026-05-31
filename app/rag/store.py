import chromadb


class ChromaStore:
    """Thin wrapper over a Chroma collection using explicit (precomputed) embeddings."""

    def __init__(self, client, collection_name: str = "company_docs") -> None:
        self.client = client
        self.collection_name = collection_name

    @classmethod
    def persistent(cls, path: str = "data/chroma", collection_name: str = "company_docs") -> "ChromaStore":
        return cls(chromadb.PersistentClient(path=path), collection_name)

    @classmethod
    def ephemeral(cls, collection_name: str = "company_docs") -> "ChromaStore":
        return cls(chromadb.EphemeralClient(), collection_name)

    def _collection(self):
        return self.client.get_or_create_collection(
            self.collection_name, metadata={"hnsw:space": "cosine"}
        )

    def reset(self):
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
        return self._collection()

    def add(self, ids, embeddings, documents, metadatas) -> None:
        self._collection().add(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
        )

    def count(self) -> int:
        return self._collection().count()

    def query(self, embedding: list[float], k: int = 4) -> list[dict]:
        res = self._collection().query(query_embeddings=[embedding], n_results=k)
        docs = res["documents"][0]
        metas = res["metadatas"][0]
        dists = res["distances"][0]
        return [
            {"text": doc, "source": (meta or {}).get("source"), "score": dist}
            for doc, meta, dist in zip(docs, metas, dists)
        ]
