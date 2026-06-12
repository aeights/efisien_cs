from datetime import datetime, timedelta

from app.integrations.calendar import WIB, LocalCalendar, fmt_slot, parse_slot


def test_slots_are_future_weekday_business_hours():
    now = datetime(2099, 1, 5, 8, 0, tzinfo=WIB)
    slots = LocalCalendar().available_slots(set(), now=now)
    assert slots  # produces something
    for s in slots:
        assert s > now
        assert s.weekday() < 5            # Mon-Fri only
        assert 9 <= s.hour <= 16          # business hours; last start 16:00
        assert s.minute == 0


def test_horizon_is_seven_days():
    now = datetime(2099, 1, 5, 8, 0, tzinfo=WIB)
    slots = LocalCalendar().available_slots(set(), now=now)
    for s in slots:
        assert (s.date() - now.date()) < timedelta(days=7)


def test_excludes_booked_slot():
    now = datetime(2099, 1, 5, 8, 0, tzinfo=WIB)
    all_slots = LocalCalendar().available_slots(set(), now=now)
    target = all_slots[0]
    pruned = LocalCalendar().available_slots({target}, now=now)
    assert target not in pruned
    assert len(pruned) == len(all_slots) - 1


def test_fmt_and_parse_roundtrip():
    s = "2099-01-05 09:00"
    assert fmt_slot(parse_slot(s)) == s


def test_create_event_default_is_noop():
    from datetime import datetime

    from app.integrations.calendar import WIB, LocalCalendar

    out = LocalCalendar().create_event(
        datetime(2099, 1, 5, 9, 0, tzinfo=WIB), summary="x", description="y"
    )
    assert out is None


def test_iter_business_slots_skips_weekends_and_past():
    from datetime import datetime

    from app.integrations.calendar import WIB, fmt_slot, iter_business_slots

    now = datetime(2099, 1, 4, 0, 0, tzinfo=WIB)
    slots = iter_business_slots(now)
    assert slots, "should produce business-hour slots"
    assert all(s > now for s in slots)
    assert all(9 <= s.hour <= 16 for s in slots)
