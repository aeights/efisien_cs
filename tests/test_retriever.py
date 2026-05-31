from app.rag.embeddings import FakeEmbedder
from app.rag.retriever import Retriever
from app.rag.store import ChromaStore


def _seeded_retriever():
    store = ChromaStore.ephemeral()
    emb = FakeEmbedder()
    store.reset()
    docs = ["Layanan kami meliputi ERP dan AI.", "Kontak kami via website."]
    store.add(
        ids=["0", "1"],
        embeddings=emb.embed_documents(docs),
        documents=docs,
        metadatas=[{"source": "services.txt"}, {"source": "contact.txt"}],
    )
    return Retriever(store, emb)


def test_search_returns_most_relevant_chunk_first():
    retriever = _seeded_retriever()
    hits = retriever.search("apa saja layanan", k=1)
    assert hits[0]["source"] == "services.txt"


def test_search_on_empty_index_returns_empty():
    store = ChromaStore.ephemeral()
    store.reset()
    retriever = Retriever(store, FakeEmbedder())
    assert retriever.search("layanan") == []
