from app.rag.store import ChromaStore


def test_add_and_query_returns_documents_and_sources():
    store = ChromaStore.ephemeral()
    store.reset()
    store.add(
        ids=["0", "1"],
        embeddings=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        documents=["layanan kami banyak", "kontak whatsapp"],
        metadatas=[{"source": "services.txt"}, {"source": "contact.txt"}],
    )
    assert store.count() == 2
    hits = store.query([0.9, 0.1, 0.0], k=2)
    assert hits[0]["text"] == "layanan kami banyak"
    assert hits[0]["source"] == "services.txt"
    assert "score" in hits[0]


def test_reset_clears_collection():
    store = ChromaStore.ephemeral()
    store.reset()
    store.add(ids=["0"], embeddings=[[1.0, 0.0]], documents=["x"], metadatas=[{"source": "a"}])
    store.reset()
    assert store.count() == 0
