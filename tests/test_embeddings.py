from app.rag.embeddings import FakeEmbedder


def test_fake_embedder_is_deterministic_and_same_dim():
    emb = FakeEmbedder()
    a = emb.embed_query("apa saja layanan kami")
    b = emb.embed_query("apa saja layanan kami")
    assert a == b
    docs = emb.embed_documents(["layanan erp", "kontak website"])
    assert len(docs) == 2
    assert len(docs[0]) == len(a)  # query and document vectors share dimension


def test_fake_embedder_reflects_shared_keywords():
    emb = FakeEmbedder()
    q = emb.embed_query("layanan")
    doc_match = emb.embed_documents(["layanan kami banyak"])[0]
    doc_other = emb.embed_documents(["kontak whatsapp"])[0]
    # the "layanan" dimension is non-zero for the matching doc, zero for the other
    idx = FakeEmbedder.VOCAB.index("layanan")
    assert q[idx] > 0 and doc_match[idx] > 0
    assert doc_other[idx] == 0
