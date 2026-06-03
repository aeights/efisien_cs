from app.integrations.email import ConsoleEmail


def test_console_email_uses_sink():
    log = []
    ConsoleEmail(sink=log.append).send("a@mail.com", "Hi", "Body")
    assert len(log) == 1
    assert "a@mail.com" in log[0]
