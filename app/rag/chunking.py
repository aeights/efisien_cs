import re


def chunk_text(text: str, max_chars: int = 600) -> list[str]:
    """Split text into chunks by grouping blank-line paragraphs up to max_chars,
    keeping a one-paragraph overlap between consecutive chunks."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        if current and current_len + len(para) > max_chars:
            chunks.append("\n\n".join(current))
            current = [current[-1]]  # overlap: keep last paragraph
            current_len = len(current[-1])
        current.append(para)
        current_len += len(para)

    if current:
        chunks.append("\n\n".join(current))
    return chunks
