import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage


class EmailAdapter(ABC):
    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> None:
        ...


class ConsoleEmail(EmailAdapter):
    """Logs the invitation instead of sending. Real SMTP swaps in later."""

    def __init__(self, sink=print) -> None:
        self._sink = sink

    def send(self, to: str, subject: str, body: str) -> None:
        self._sink(f"[EMAIL] to={to} | {subject}\n{body}")


class SmtpEmail(EmailAdapter):
    """Sends real email via SMTP (e.g. Gmail with an App Password)."""

    def __init__(self, *, host, port, user, password, sender, smtp_factory=smtplib.SMTP):
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._sender = sender or user
        self._smtp_factory = smtp_factory

    def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = self._sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        with self._smtp_factory(self._host, self._port) as smtp:
            smtp.starttls()
            smtp.login(self._user, self._password)
            smtp.send_message(msg)
