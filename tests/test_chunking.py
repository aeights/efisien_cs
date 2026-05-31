from app.rag.chunking import chunk_text


def test_short_text_is_single_chunk():
    chunks = chunk_text("Halo dunia.\n\nIni singkat.", max_chars=600)
    assert len(chunks) == 1
    assert "Halo dunia." in chunks[0]


def test_strips_decoration_lines():
    text = (
        "================\n"
        "1. TENTANG KAMI\n"
        "----------------\n"
        "Efisien adalah partner transformasi digital.\n\n"
        "Layanan kami banyak."
    )
    chunks = chunk_text(text, max_chars=600)
    joined = "\n".join(chunks)
    assert "====" not in joined
    assert "----" not in joined
    assert "1. TENTANG KAMI" in joined
    assert "partner transformasi digital" in joined


def test_keeps_numbered_section_together():
    text = (
        "1. TENTANG KAMI\nKami adalah perusahaan teknologi.\n\n"
        "4. LAYANAN\n[1] ERP\n[2] AI\n[3] Computer Vision"
    )
    chunks = chunk_text(text, max_chars=1200)
    layanan = [c for c in chunks if "4. LAYANAN" in c][0]
    assert "[1] ERP" in layanan and "[3] Computer Vision" in layanan
    # the about section is a separate chunk
    assert any("1. TENTANG KAMI" in c and "4. LAYANAN" not in c for c in chunks)


def test_groups_paragraphs_with_overlap():
    text = "\n\n".join(["a" * 100, "b" * 100, "c" * 100, "d" * 100])
    chunks = chunk_text(text, max_chars=250)
    assert len(chunks) == 3
    assert chunks[0].startswith("a" * 100)
    # overlap: last paragraph of a chunk reappears at the start of the next
    assert "b" * 100 in chunks[0] and "b" * 100 in chunks[1]
    assert "c" * 100 in chunks[1] and "c" * 100 in chunks[2]
