"""
KTP direct rates from the live SiteMinder booking engine
(book-directonline.com/properties/kosciuszkotouristpark-1).

Endpoint: /api/properties/{channel}/room-types/{id}/availability
          ?checkInsFrom=..&checkInsTo=..&adults=..&children=..&infants=0&los=N

How it behaves (checked against the live engine):
- A multi-day range (from < to) returns the nightly calendar: the 1-night
  base price, units left and any min-stay / sold-out constraint per date. It
  ignores adults and los, so it is only used for the base nightly rate.
- A single date (from == to) honours adults, children and los. Used for
  Fri->Sun 2-night prices (includes Stay & Save where it applies) and for
  extra-guest charges.

KTP charges an extra guest the same whether adult or child. Extras are read
once per week (first bookable Sun-Thu night) and applied to that week.
"""

import logging
from datetime import date, timedelta

import config
from .common import nearest_week, record, week_key

log = logging.getLogger(__name__)
PARK = "ktp"
WARMUP = f"{config.KTP_BASE}/properties/{config.KTP_CHANNEL}"


def _url(room_id, frm, to, adults=2, children=0, los=1):
    return (f"{config.KTP_BASE}/api/properties/{config.KTP_CHANNEL}/room-types/{room_id}/availability"
            f"?checkInsFrom={frm.isoformat()}&checkInsTo={to.isoformat()}"
            f"&adults={adults}&children={children}&infants=0&los={los}")


def _chunks(start, end_incl, size):
    d = start
    while d <= end_incl:
        e = min(d + timedelta(days=size - 1), end_incl)
        yield d, e
        d = e + timedelta(days=1)


def parse_range(payload):
    """-> {date_iso: row} with price, units, can_check_in, constraint, min_stay."""
    out = {}
    for row in (payload or {}).get("result", []):
        d = row["date"][:10]
        c = row.get("checkOutConstraint") or {}
        out[d] = {
            "price": row.get("price") or 0,
            "units": row.get("totalAvailability"),
            "can_check_in": row.get("canCheckIn", False),
            "constraint": row.get("availabilityConstraint"),
            "min_stay": row.get("constraintStayDays") or c.get("minStay") or 1,
        }
    return out


def single(payload, d: date):
    return parse_range(payload).get(d.isoformat())


def _ok(row):
    return bool(row and row["price"] and row["units"] and row["can_check_in"])


def _note(row, nights):
    if not row:
        return "no data"
    if _ok(row):
        return ""
    if (row["constraint"] or "").startswith("sold-out"):
        return "sold out"
    if row["constraint"] == "min-stay-constraint" or (row["min_stay"] or 1) > nights:
        return f"min {row['min_stay']} nights"
    if not row["can_check_in"]:
        return "closed to arrival"
    return "sold out"


def extras_probe_dates(start, days, cal):
    """First bookable Sun-Thu night of each week in the window -> {week_sunday: date}."""
    picks = {}
    for i in range(days):
        d = start + timedelta(days=i)
        if d.weekday() in (4, 5):
            continue
        wk = week_key(d)
        if wk not in picks and _ok(cal.get(d.isoformat())):
            picks[wk] = d
    return picks


def build_records(room_id, room_name, start, days, cal, weekends, extras):
    """cal: {date_iso: row} nightly calendar; weekends: {fri_iso: row} (los=2);
    extras: {week_sunday: (extra_adult, extra_child)} per night."""
    recs = []
    for i in range(days):
        d = start + timedelta(days=i)
        k = d.isoformat()
        b = cal.get(k)
        ea, ec = nearest_week(extras, week_key(d))
        price, estimated = (b["price"] if b and b["price"] else None), False
        w = weekends.get(k)
        if price is None and b and b["min_stay"] == 2 and w and w["price"]:
            price, estimated = w["price"] / 2, True     # nightly equivalent of the 2-night price
        recs.append(record(PARK, room_id, room_name, "night", d, 1, price=price, rack=price,
                           bookable=_ok(b), note=_note(b, 1), units_left=b["units"] if b else None,
                           extra_adult=ea, extra_child=ec, estimated=estimated))
        if d.weekday() == 4:
            sat = (cal.get((d + timedelta(days=1)).isoformat()) or {}).get("price")
            fri = b["price"] if b else None
            recs.append(record(PARK, room_id, room_name, "weekend", d, 2,
                               price=(w["price"] if w and w["price"] else None),
                               rack=(fri + sat) if fri and sat else None,
                               bookable=_ok(w), note=_note(w, 2),
                               units_left=w["units"] if w else None,
                               extra_adult=ea, extra_child=ec))
    return recs


def collect(fetcher, mapping, start: date, days: int):
    end = start + timedelta(days=days - 1)
    get = lambda url: fetcher.get_json(PARK, WARMUP, url)
    recs = []
    for cat in mapping["categories"]:
        rid, name = cat["ktp_room_id"], cat["label"]
        cal = {}
        for frm, to in _chunks(start, end, config.KTP_RANGE_MAX_DAYS):
            if frm == to:                      # a 1-day chunk would be read as a single-date query
                frm = frm - timedelta(days=1)
            cal.update(parse_range(get(_url(rid, frm, to))))
        weekends = {}
        for i in range(days):
            d = start + timedelta(days=i)
            if d.weekday() == 4:
                weekends[d.isoformat()] = single(get(_url(rid, d, d, 2, 0, 2)), d)
        extras = {}
        for wk, d in extras_probe_dates(start, days, cal).items():
            base = cal[d.isoformat()]["price"]
            pa = single(get(_url(rid, d, d, 3, 0, 1)), d)
            pc = single(get(_url(rid, d, d, 2, 1, 1)), d)
            extras[wk] = ((pa["price"] - base) if pa and pa["price"] else None,
                          (pc["price"] - base) if pc and pc["price"] else None)
        recs.extend(build_records(rid, name, start, days, cal, weekends, extras))
        log.info("ktp %s done (%d records so far)", name, len(recs))
    return recs
