from app.repositories.notification_repo import NotificationRepository


def test_create_notification_is_sent(session):
    n = NotificationRepository(session).create(
        "manager", reason="komplain pembayaran", payload={"name": "Budi", "phone": "0870"}
    )
    assert n.id is not None
    assert n.target_role == "manager"
    assert n.status == "sent"
    assert n.reason == "komplain pembayaran"
    assert n.payload == {"name": "Budi", "phone": "0870"}
