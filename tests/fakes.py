class FakeCalendar:
    """Returns a fixed slot list (minus booked) regardless of `now` — deterministic."""

    def __init__(self, slots):
        self._slots = list(slots)

    def available_slots(self, booked, *, now):
        return [s for s in self._slots if s not in booked]


class FakeEmail:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append((to, subject, body))
