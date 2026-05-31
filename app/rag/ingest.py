import pathlib

from app.rag.chunking import chunk_text
from app.rag.embeddings import Embedder
from app.rag.store import ChromaStore


def load_documents(docs_dir: str = "data/docs") -> list[tuple[str, str]]:
    """Return [(source_filename, text), ...] for every *.txt in docs_dir."""
    out: list[tuple[str, str]] = []
    for path in sorted(pathlib.Path(docs_dir).glob("*.txt")):
        out.append((path.name, path.read_text(encoding="utf-8")))
    return out


def build_chunks(documents: list[tuple[str, str]]) -> list[dict]:
    chunks: list[dict] = []
    for source, text in documents:
        for i, piece in enumerate(chunk_text(text)):
            chunks.append(
                {"id": f"{source}::{i}", "text": piece, "source": source, "chunk_index": i}
            )
    return chunks


def ingest(store: ChromaStore, embedder: Embedder, docs_dir: str = "data/docs") -> dict:
    documents = load_documents(docs_dir)
    chunks = build_chunks(documents)
    store.reset()
    if chunks:
        embeddings = embedder.embed_documents([c["text"] for c in chunks])
        store.add(
            ids=[c["id"] for c in chunks],
            embeddings=embeddings,
            documents=[c["text"] for c in chunks],
            metadatas=[
                {"source": c["source"], "chunk_index": c["chunk_index"]} for c in chunks
            ],
        )
    return {"files": len(documents), "chunks": len(chunks)}
