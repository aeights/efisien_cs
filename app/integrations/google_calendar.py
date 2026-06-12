from datetime import datetime, timedelta

from app.integrations.calendar import (
    CalendarAdapter,
    fmt_slot,
    iter_business_slots,
    to_wib,
)


class GoogleCalendar(CalendarAdapter):
    """Reads freebusy and creates events on a Google Calendar via an injected service."""

    def __init__(self, service, calendar_id: str) -> None:
        self._service = service
        self._calendar_id = calendar_id

    def available_slots(self, booked, *, now):
        slots = iter_business_slots(now)
        if not slots:
            return []
        resp = (
            self._service.freebusy()
            .query(
                body={
                    "timeMin": to_wib(now).isoformat(),
                    "timeMax": (slots[-1] + timedelta(hours=1)).isoformat(),
                    "items": [{"id": self._calendar_id}],
                }
            )
            .execute()
        )
        busy_raw = resp.get("calendars", {}).get(self._calendar_id, {}).get("busy", [])
        busy = [
            (datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"]))
            for b in busy_raw
        ]
        booked_keys = {fmt_slot(b) for b in booked}
        result = []
        for s in slots:
            if fmt_slot(s) in booked_keys:
                continue
            if any(bs <= s < be for bs, be in busy):
                continue
            result.append(s)
        return result

    def create_event(self, start, *, summary, description):
        body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": to_wib(start).isoformat(), "timeZone": "Asia/Jakarta"},
            "end": {
                "dateTime": to_wib(start + timedelta(hours=1)).isoformat(),
                "timeZone": "Asia/Jakarta",
            },
        }
        event = self._service.events().insert(calendarId=self._calendar_id, body=body).execute()
        return event.get("id")


def build_google_calendar(settings) -> GoogleCalendar:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        settings.google_service_account_file,
        scopes=["https://www.googleapis.com/auth/calendar"],
    )
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return GoogleCalendar(service, settings.google_calendar_id)
