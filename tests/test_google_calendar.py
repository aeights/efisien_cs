from datetime import datetime, timedelta

from app.integrations.calendar import WIB, fmt_slot, iter_business_slots
from app.integrations.google_calendar import GoogleCalendar

CAL = "cal@example.com"


class _FakeFreebusy:
    def __init__(self, busy):
        self._busy = busy

    def query(self, body=None):
        self._body = body
        return self

    def execute(self):
        return {"calendars": {CAL: {"busy": self._busy}}}


class _FakeEvents:
    def __init__(self, store):
        self._store = store

    def insert(self, calendarId=None, body=None):
        self._store["calendarId"] = calendarId
        self._store["body"] = body
        return self

    def execute(self):
        return {"id": "evt-xyz"}


class _FakeService:
    def __init__(self, busy):
        self._fb = _FakeFreebusy(busy)
        self.store = {}

    def freebusy(self):
        return self._fb

    def events(self):
        return _FakeEvents(self.store)


def test_available_slots_excludes_busy():
    now = datetime(2099, 1, 4, 0, 0, tzinfo=WIB)
    target = iter_business_slots(now)[0]
    busy = [{"start": target.isoformat(), "end": (target + timedelta(hours=1)).isoformat()}]
    cal = GoogleCalendar(_FakeService(busy), CAL)
    keys = {fmt_slot(s) for s in cal.available_slots(set(), now=now)}
    assert fmt_slot(target) not in keys
    assert fmt_slot(iter_business_slots(now)[1]) in keys


def test_create_event_inserts_and_returns_id():
    cal = GoogleCalendar(_FakeService([]), CAL)
    eid = cal.create_event(
        datetime(2099, 1, 5, 9, 0, tzinfo=WIB), summary="Konsultasi", description="Link: x"
    )
    assert eid == "evt-xyz"
