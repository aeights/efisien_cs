from app.rag.chunking import chunk_text


def test_short_text_is_single_chunk():
    chunks = chunk_text("Halo dunia.\n\nIni singkat.", max_chars=600)
    assert len(chunks) == 1
    assert "Halo dunia." in chunks[0]


def test_groups_paragraphs_with_overlap():
    text = "\n\n".join(["a" * 100, "b" * 100, "c" * 100, "d" * 100])
    chunks = chunk_text(text, max_chars=250)
    assert len(chunks) == 3
    assert chunks[0].startswith("a" * 100)
    # overlap: last paragraph of a chunk reappears at the start of the next
    assert "b" * 100 in chunks[0] and "b" * 100 in chunks[1]
    assert "c" * 100 in chunks[1] and "c" * 100 in chunks[2]
