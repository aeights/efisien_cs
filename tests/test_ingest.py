from app.rag.embeddings import FakeEmbedder
from app.rag.ingest import build_chunks, ingest, load_documents
from app.rag.store import ChromaStore


def test_load_and_chunk_documents(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "services.txt").write_text(
        "Layanan kami ERP dan AI.\n\nKami juga buat website.", encoding="utf-8"
    )
    documents = load_documents(str(docs_dir))
    assert documents[0][0] == "services.txt"

    chunks = build_chunks(documents)
    assert chunks[0]["source"] == "services.txt"
    assert chunks[0]["chunk_index"] == 0
    assert "id" in chunks[0] and "text" in chunks[0]


def test_ingest_builds_index(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "services.txt").write_text("Layanan kami ERP.", encoding="utf-8")
    (docs_dir / "contact.txt").write_text("Kontak via website.", encoding="utf-8")

    store = ChromaStore.ephemeral()
    stats = ingest(store, FakeEmbedder(), docs_dir=str(docs_dir))

    assert stats["files"] == 2
    assert stats["chunks"] >= 2
    assert store.count() == stats["chunks"]


def test_ingest_is_idempotent(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.txt").write_text("Layanan ERP.", encoding="utf-8")
    store = ChromaStore.ephemeral()
    ingest(store, FakeEmbedder(), docs_dir=str(docs_dir))
    count_after_first = store.count()
    ingest(store, FakeEmbedder(), docs_dir=str(docs_dir))
    assert store.count() == count_after_first  # rebuild, not duplicate
