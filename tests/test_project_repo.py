from app.models.user import User
from app.repositories.project_repo import ProjectRepository


def _user(session):
    u = User(name="Klien", phone="0850")
    session.add(u)
    session.flush()
    return u


def test_create_and_list_for_user(session):
    u = _user(session)
    repo = ProjectRepository(session)
    repo.create(
        u.id, name="POS Toko A", type="POS", progress=60,
        status="in_progress", details={"backend": "done"},
    )
    repo.create(u.id, name="Website Profil", type="Website", progress=20)
    projects = repo.list_for_user(u.id)
    assert [p.name for p in projects] == ["POS Toko A", "Website Profil"]
    assert projects[0].progress == 60
    assert projects[0].details == {"backend": "done"}
    assert projects[1].status == "in_progress"


def test_list_for_user_empty(session):
    u = _user(session)
    assert ProjectRepository(session).list_for_user(u.id) == []
