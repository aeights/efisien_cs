import re

# Lines made up only of decoration characters (===, ---, ___, ***) carry no
# semantic meaning and pollute embeddings, so we drop them before chunking.
_DECORATION_CHARS = set("=-_*~ ")

# A numbered section header like "1. TENTANG KAMI" or "4. LAYANAN".
_SECTION_RE = re.compile(r"^\d+\.\s+\S")


def _clean(text: str) -> str:
    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and set(stripped) <= _DECORATION_CHARS:
            continue  # pure divider/decoration line
        kept.append(line)
    return "\n".join(kept)


def _split_sections(text: str) -> list[str]:
    """Split on numbered section headers so each section stays coherent."""
    sections: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if _SECTION_RE.match(line.strip()) and current:
            sections.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current).strip())
    return [s for s in sections if s]


def _paragraph_chunks(text: str, max_chars: int) -> list[str]:
    """Group blank-line paragraphs up to max_chars, with one-paragraph overlap."""
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


def chunk_text(text: str, max_chars: int = 1200) -> list[str]:
    """Chunk a document for RAG: strip decoration lines, keep each numbered
    section together, and only paragraph-split sections that exceed max_chars."""
    text = _clean(text)
    chunks: list[str] = []
    for section in _split_sections(text):
        if len(section) <= max_chars:
            chunks.append(section)
        else:
            chunks.extend(_paragraph_chunks(section, max_chars))
    return chunks
