from app.repositories.user_repo import UserRepository


def test_creates_new_user_when_none_matches(session):
    repo = UserRepository(session)
    user = repo.get_or_create(name="Budi", phone="08123456789", email=None)
    session.flush()
    assert user.id is not None
    assert user.name == "Budi"
    assert user.phone == "08123456789"


def test_matches_existing_user_by_phone(session):
    repo = UserRepository(session)
    first = repo.get_or_create(name="Budi", phone="08123456789", email=None)
    session.flush()
    again = repo.get_or_create(name="Budi Updated", phone="08123456789", email=None)
    assert again.id == first.id
    assert again.name == "Budi Updated"  # name refreshed on return


def test_matches_existing_user_by_email(session):
    repo = UserRepository(session)
    first = repo.get_or_create(name="Sari", phone=None, email="sari@mail.com")
    session.flush()
    again = repo.get_or_create(name=None, phone=None, email="sari@mail.com")
    assert again.id == first.id
