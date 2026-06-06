from app.models.user import User
from app.repositories.client_fact_repo import ClientFactRepository


def _user(session):
    u = User(name="Klien", phone="0870")
    session.add(u)
    session.flush()
    return u


def test_upsert_creates_then_updates(session):
    u = _user(session)
    repo = ClientFactRepository(session)
    repo.upsert(u.id, "nama", "Budi")
    repo.upsert(u.id, "perusahaan", "Toko Maju")
    repo.upsert(u.id, "nama", "Andi")  # same key -> update, not insert
    facts = repo.list_for_user(u.id)
    assert len(facts) == 2
    by_key = {f.key: f.value for f in facts}
    assert by_key["nama"] == "Andi"
    assert by_key["perusahaan"] == "Toko Maju"


def test_list_for_user_empty(session):
    u = _user(session)
    assert ClientFactRepository(session).list_for_user(u.id) == []
