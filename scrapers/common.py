from datetime import date, timedelta


def week_key(d: date) -> date:
    """The Sunday on or before d."""
    return d - timedelta(days=(d.weekday() + 1) % 7)


def extras_probe_nights(plan):
    """First Sun-Thu 1-night stay of each week in the plan -> set of check-in dates.
    Extra-guest charges are read on these nights only and applied to the whole week."""
    picks = {}
    for stay, d, _ in plan:
        if stay == "night" and d.weekday() not in (4, 5):
            picks.setdefault(week_key(d), d)
    return set(picks.values())


def nearest_week(by_week: dict, wk: date, default=(None, None)):
    """by_week[wk], else the value for the closest week (extras rarely change)."""
    if wk in by_week:
        return by_week[wk]
    if not by_week:
        return default
    return by_week[min(by_week, key=lambda k: (abs((k - wk).days), k < wk))]


def stay_plan(start: date, days: int):
    """[(stay_type, check_in, nights)] - every night as 1 night, every Friday as Fri->Sun."""
    plan = []
    for i in range(days):
        d = start + timedelta(days=i)
        plan.append(("night", d, 1))
        if d.weekday() == 4:
            plan.append(("weekend", d, 2))
    return plan


def rnd(x):
    return None if x is None else round(float(x), 2)


def record(park, room_id, room_name, stay, check_in, nights, *, price=None, rack=None,
           bookable=False, note="", units_left=None, extra_adult=None, extra_child=None,
           estimated=False):
    """One priced stay. price = what we compare on (member rate for competitors,
    lowest public price for KTP). rack = non-member / standard price.
    extra_adult / extra_child are per person, per night, above 2 adults."""
    return {
        "park": park,
        "room_id": str(room_id),
        "room_name": room_name,
        "stay": stay,
        "check_in": check_in.isoformat() if isinstance(check_in, date) else check_in,
        "nights": nights,
        "price": rnd(price),
        "rack": rnd(rack),
        "bookable": bool(bookable),
        "note": note,
        "units_left": units_left,
        "extra_adult": rnd(extra_adult),
        "extra_child": rnd(extra_child),
        "estimated": bool(estimated),
    }


def per_night_diff(a, b, nights):
    if a is None or b is None:
        return None
    return (a - b) / nights
