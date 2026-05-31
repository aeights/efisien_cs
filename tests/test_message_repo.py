from app.repositories.message_repo import MessageRepository
from app.repositories.user_repo import UserRepository


def test_add_and_fetch_recent_in_chronological_order(session):
    user = UserRepository(session).get_or_create(phone="0811")
    session.flush()
    repo = MessageRepository(session)
    repo.add(user.id, "user", "halo")
    repo.add(user.id, "assistant", "halo juga")
    repo.add(user.id, "user", "apa layanan kalian?")

    recent = repo.recent(user.id, limit=15)
    assert [m.content for m in recent] == ["halo", "halo juga", "apa layanan kalian?"]
    assert [m.role for m in recent] == ["user", "assistant", "user"]


def test_recent_respects_limit_and_keeps_latest(session):
    user = UserRepository(session).get_or_create(phone="0811")
    session.flush()
    repo = MessageRepository(session)
    for i in range(5):
        repo.add(user.id, "user", f"msg-{i}")

    recent = repo.recent(user.id, limit=2)
    assert [m.content for m in recent] == ["msg-3", "msg-4"]
