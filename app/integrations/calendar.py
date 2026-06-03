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


class CalendarAdapter(ABC):
    @abstractmethod
    def available_slots(self, booked: set[datetime], *, now: datetime) -> list[datetime]:
        ...


class LocalCalendar(CalendarAdapter):
    """Business-hour slots for the next HORIZON_DAYS, minus booked meetings."""

    def available_slots(self, booked: set[datetime], *, now: datetime) -> list[datetime]:
        booked_keys = {fmt_slot(b) for b in booked}
        now_w = to_wib(now)
        start = now_w.date()
        result: list[datetime] = []
        for offset in range(HORIZON_DAYS):
            day = start + timedelta(days=offset)
            if day.weekday() >= 5:  # Sat=5, Sun=6
                continue
            for hour in range(WORK_START, WORK_END):  # 9..16
                slot = datetime(day.year, day.month, day.day, hour, 0, tzinfo=WIB)
                if slot <= now_w:
                    continue
                if fmt_slot(slot) in booked_keys:
                    continue
                result.append(slot)
        return result
