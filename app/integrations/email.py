from abc import ABC, abstractmethod


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
