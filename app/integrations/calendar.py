from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

WIB = ZoneInfo("Asia/Jakarta")
SLOT_FMT = "%Y-%m-%d %H:%M"

WORK_START = 9    # first slot starts 09:00
WORK_END = 17     # exclusive: last slot starts 16:00
HORIZON_DAYS = 7


def to_wib(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=WIB)
    return dt.astimezone(WIB)


def now_wib() -> datetime:
    return datetime.now(WIB)


def fmt_slot(dt: datetime) -> str:
    return to_wib(dt).strftime(SLOT_FMT)


def parse_slot(s: str) -> datetime:
    return datetime.strptime(s, SLOT_FMT).replace(tzinfo=WIB)


def iter_business_slots(now: datetime) -> list[datetime]:
    """All future business-hour slots within the horizon (no booking awareness)."""
    now_w = to_wib(now)
    start = now_w.date()
    result: list[datetime] = []
    for offset in range(HORIZON_DAYS):
        day = start + timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        for hour in range(WORK_START, WORK_END):
            slot = datetime(day.year, day.month, day.day, hour, 0, tzinfo=WIB)
            if slot <= now_w:
                continue
            result.append(slot)
    return result


class CalendarAdapter(ABC):
    @abstractmethod
    def available_slots(self, booked: set[datetime], *, now: datetime) -> list[datetime]:
        ...

    def create_event(self, start: datetime, *, summary: str, description: str) -> str | None:
        """Optional: create a real calendar event; default no-op returns None."""
        return None


class LocalCalendar(CalendarAdapter):
    """Business-hour slots for the next HORIZON_DAYS, minus booked meetings."""

    def available_slots(self, booked: set[datetime], *, now: datetime) -> list[datetime]:
        booked_keys = {fmt_slot(b) for b in booked}
        return [s for s in iter_business_slots(now) if fmt_slot(s) not in booked_keys]
