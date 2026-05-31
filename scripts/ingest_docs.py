import pathlib
import sys

# Allow running as `python scripts/ingest_docs.py` from the project root.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.rag.embeddings import GeminiEmbedder  # noqa: E402
from app.rag.ingest import ingest  # noqa: E402
from app.rag.store import ChromaStore  # noqa: E402


def main() -> None:
    store = ChromaStore.persistent()
    stats = ingest(store, GeminiEmbedder())
    print(f"{stats['files']} file, {stats['chunks']} chunk, tersimpan ke data/chroma/")


if __name__ == "__main__":
    main()
