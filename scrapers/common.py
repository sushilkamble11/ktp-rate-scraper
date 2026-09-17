from datetime import date, timedelta

STATUSES = ("open", "sold out", "min stay", "not bookable", "not open")


def rnd(x):
    return None if x is None else round(float(x), 2)


def night(park, room_id, room_name, d, *, rate=None, rack=None, units=None,
          status="open", min_stay=None):
    """One night's price for one room type.
    rate = what we compare on (member rate for competitors, public rate for KTP).
    rack = public / non-member rate. status: open | sold out | min stay | not bookable (rate loaded, bookings
    not open yet) | not open (no rate)."""
    import config
    if (rack or 0) >= config.PLACEHOLDER_RATE or (rate or 0) >= config.PLACEHOLDER_RATE:
        rate, rack, status = None, None, "not open"      # block-out placeholder, not a price
    return {
        "park": park,
        "room_id": str(room_id),
        "room_name": room_name,
        "date": d.isoformat() if isinstance(d, date) else d,
        "rate": rnd(rate),
        "rack": rnd(rack),
        "units": units,
        "status": status,
        "min_stay": min_stay,
    }


def extra(park, room_id, month, adult, child):
    """Extra-guest charge per person per night above 2 adults, sampled for a month."""
    return {"park": park, "room_id": str(room_id), "month": month,
            "adult": rnd(adult), "child": rnd(child)}


def chunks(start: date, end_incl: date, size: int):
    d = start
    while d <= end_incl:
        e = min(d + timedelta(days=size - 1), end_incl)
        yield d, e
        d = e + timedelta(days=1)


def days(start: date, end_incl: date):
    d = start
    while d <= end_incl:
        yield d
        d += timedelta(days=1)


def month_key(d) -> str:
    return (d.isoformat() if isinstance(d, date) else d)[:7]


def first_weeknights(dates):
    """First Sun-Thu date in each month from an iterable of dates -> {month: date}."""
    out = {}
    for d in sorted(dates):
        if d.weekday() in (4, 5):
            continue
        out.setdefault(month_key(d), d)
    return out
