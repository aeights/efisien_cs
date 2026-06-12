class FakeCalendar:
    """Returns a fixed slot list (minus booked) regardless of `now` — deterministic."""

    def __init__(self, slots, event_id=None):
        self._slots = list(slots)
        self._event_id = event_id
        self.created = []

    def available_slots(self, booked, *, now):
        return [s for s in self._slots if s not in booked]

    def create_event(self, start, *, summary, description):
        self.created.append((start, summary, description))
        return self._event_id


class FakeEmail:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append((to, subject, body))
