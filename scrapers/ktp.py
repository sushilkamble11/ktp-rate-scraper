"""
KTP direct rates from the live SiteMinder booking engine
(book-directonline.com/properties/kosciuszkotouristpark-1).

Endpoint: /api/properties/{channel}/room-types/{id}/availability
          ?checkInsFrom=..&checkInsTo=..&adults=..&children=..&infants=0&los=N

How it behaves (checked against the live engine):
- A multi-day range returns the nightly calendar: 1-night public price, units
  left and any constraint (min-stay / sold-out / stop-sell). It ignores
  adults and los. A min-stay night comes back with price 0.
- A single date (from == to) honours adults, children and los. Used to price
  min-stay nights (price for the minimum stay / nights) and extra guests.

KTP charges an extra guest the same whether adult or child.
"""

import logging
from datetime import date, timedelta

import config
from .common import chunks, days, extra, first_weeknights, month_key, night

log = logging.getLogger(__name__)
PARK = "ktp"
WARMUP = f"{config.KTP_BASE}/properties/{config.KTP_CHANNEL}"


def _url(room_id, frm, to, adults=2, children=0, los=1):
    return (f"{config.KTP_BASE}/api/properties/{config.KTP_CHANNEL}/room-types/{room_id}/availability"
            f"?checkInsFrom={frm.isoformat()}&checkInsTo={to.isoformat()}"
            f"&adults={adults}&children={children}&infants=0&los={los}")


def parse_range(payload):
    """-> {date_iso: row}"""
    out = {}
    for row in (payload or {}).get("result", []):
        c = row.get("checkOutConstraint") or {}
        out[row["date"][:10]] = {
            "price": row.get("price") or 0,
            "units": row.get("totalAvailability"),
            "can_check_in": row.get("canCheckIn", False),
            "constraint": row.get("availabilityConstraint") or "",
            "min_stay": row.get("constraintStayDays") or c.get("minStay") or 1,
        }
    return out


def status_of(row):
    if not row:
        return "not open"
    c = row["constraint"]
    if c.startswith("stop-sell"):
        return "not open"
    if c.startswith("sold-out"):
        return "sold out"
    if c.startswith("min-stay"):
        return "min stay"
    if row["price"] and row["units"] and row["can_check_in"]:
        return "open"
    return "sold out" if row["price"] else "not open"


def build_nights(room_id, name, dates, cal, min_stay_prices):
    """cal: {iso: row}; min_stay_prices: {iso: nightly price} for min-stay nights."""
    out = []
    for d in dates:
        k = d.isoformat()
        row = cal.get(k)
        st = status_of(row)
        rate = row["price"] if row and row["price"] else None
        if st == "min stay" and rate is None:
            rate = min_stay_prices.get(k)
        out.append(night(PARK, room_id, name, d, rate=rate, rack=rate,
                         units=row["units"] if row else None, status=st,
                         min_stay=row["min_stay"] if st == "min stay" else None))
    return out


def collect(fetcher, mapping, start: date, end: date):
    get = lambda url: fetcher.get_json(PARK, WARMUP, url)
    nights, extras = [], []
    for cat in mapping["categories"]:
        rid, name = cat["ktp_room_id"], cat["label"]
        cal = {}
        for frm, to in chunks(start, end, config.KTP_RANGE_DAYS):
            if frm == to:                       # 1-day range would be read as a single-date query
                frm -= timedelta(days=1)
            cal.update(parse_range(get(_url(rid, frm, to))))
        # min-stay nights: price the minimum stay and divide
        ms = {}
        for d in days(start, end):
            row = cal.get(d.isoformat())
            if row and status_of(row) == "min stay" and not row["price"]:
                los = max(2, int(row["min_stay"] or 2))
                one = parse_range(get(_url(rid, d, d, 2, 0, los))).get(d.isoformat())
                if one and one["price"]:
                    ms[d.isoformat()] = one["price"] / los
        nights.extend(build_nights(rid, name, list(days(start, end)), cal, ms))
        # extra guests, one open weeknight a month
        open_days = [d for d in days(start, end) if status_of(cal.get(d.isoformat())) == "open"]
        for month, d in first_weeknights(open_days).items():
            base = cal[d.isoformat()]["price"]
            pa = parse_range(get(_url(rid, d, d, 3, 0, 1))).get(d.isoformat())
            pc = parse_range(get(_url(rid, d, d, 2, 1, 1))).get(d.isoformat())
            extras.append(extra(PARK, rid, month,
                                (pa["price"] - base) if pa and pa["price"] else None,
                                (pc["price"] - base) if pc and pc["price"] else None))
        log.info("ktp %s: %d open nights, %d min-stay priced", name, len(open_days), len(ms))
    return nights, extras
