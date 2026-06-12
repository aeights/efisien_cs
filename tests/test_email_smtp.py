from app.integrations.email import SmtpEmail


class _FakeSMTP:
    instances = []

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.started_tls = False
        self.logged_in = None
        self.sent = None
        _FakeSMTP.instances.append(self)

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, msg):
        self.sent = msg

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_smtp_email_sends():
    _FakeSMTP.instances = []
    mailer = SmtpEmail(
        host="smtp.gmail.com", port=587, user="me@gmail.com",
        password="app-pass", sender="me@gmail.com", smtp_factory=_FakeSMTP,
    )
    mailer.send("client@example.com", "Undangan", "Jadwal: besok 09:00")
    smtp = _FakeSMTP.instances[-1]
    assert (smtp.host, smtp.port) == ("smtp.gmail.com", 587)
    assert smtp.started_tls is True
    assert smtp.logged_in == ("me@gmail.com", "app-pass")
    assert smtp.sent["To"] == "client@example.com"
    assert smtp.sent["Subject"] == "Undangan"
    assert smtp.sent["From"] == "me@gmail.com"
    assert "Jadwal: besok 09:00" in smtp.sent.get_content()
