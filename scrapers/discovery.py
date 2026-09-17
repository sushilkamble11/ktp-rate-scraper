"""
Discovery Parks Jindabyne (G'day Group booking API, park code NJIN).

GET {API}/parks/NJIN/availability?checkIn=..&checkOut=..&adults=..&children=..&infants=0
with header Gday-Caller: DhpWeb - the same call their park page makes.

Every room type in the response (available or unavailable) carries a nightly
price calendar covering the next 12 months. One call therefore gives every
room's public nightly rate for the whole year; member rate = 10% off (capped
at $50 a booking, which never bites on a single night).

Extras: a 1-night stay at 3 adults + 1 child on one weeknight a month;
the offer's rateBreakdown itemises additionalAdult / additionalChild.
"""

import logging
from datetime import date, timedelta

import config
from .common import days, extra, first_weeknights, month_key, night

log = logging.getLogger(__name__)
PARK = "discovery"
HEADERS = {"Gday-Caller": config.DISCOVERY_CALLER}


def _url(check_in, nights, adults, children):
    co = check_in + timedelta(days=nights)
    return (f"{config.DISCOVERY_API}/parks/{config.DISCOVERY_PARK_CODE}/availability"
            f"?checkIn={check_in.isoformat()}&checkOut={co.isoformat()}"
            f"&adults={adults}&children={children}&infants=0")


def member(rack):
    if not rack:
        return None
    return rack - min(rack * config.DISCOVERY_MEMBER_PCT / 100, config.DISCOVERY_MEMBER_CAP)


def parse_calendar(payload, start, end):
    """-> list of night records for every room type."""
    res = (payload or {}).get("result") or {}
    rooms = (res.get("available") or []) + (res.get("unavailable") or [])
    out = []
    for room in rooms:
        cal = {a["date"][:10]: a for a in room.get("availability") or []}
        for d in days(start, end):
            a = cal.get(d.isoformat())
            price = (a or {}).get("price") or 0
            if not a or not price:
                st, rate = "not open", None
            elif a.get("isAvailable") is False:
                st, rate = "sold out", member(price)
            else:
                st, rate = "open", member(price)
            out.append(night(PARK, room["code"], room["name"], d, rate=rate,
                             rack=price or None, status=st))
    return out


def parse_extras(payload, nights=1):
    res = (payload or {}).get("result") or {}
    out = {}
    for room in res.get("available") or []:
        offers = room.get("offers") or []
        o = next((x for x in offers if x.get("templateCode") == "MemberOffer"), offers[0] if offers else None)
        rb = ((o or {}).get("price") or {}).get("rateBreakdown")
        if rb is not None:
            out[room["code"]] = (rb.get("additionalAdult", 0) / nights,
                                 rb.get("additionalChild", 0) / nights)
    return out


def collect(fetcher, mapping, start: date, end: date):
    get = lambda url: fetcher.get_json(PARK, config.DISCOVERY_PAGE, url, HEADERS)
    nights = parse_calendar(get(_url(start, 1, config.ADULTS, 0)), start, end)
    wanted = {c["competitors"][PARK]["room_id"] for c in mapping["categories"]
              if c["competitors"].get(PARK, {}).get("room_id")}
    open_days = sorted({date.fromisoformat(n["date"]) for n in nights
                        if n["status"] == "open" and n["room_id"] in wanted})
    extras = []
    for month, d in first_weeknights(open_days).items():
        for code, (a, c) in parse_extras(get(_url(d, 1, 3, 1))).items():
            extras.append(extra(PARK, code, month, a, c))
    seen = {n["room_id"] for n in nights}
    if wanted - seen:
        log.warning("discovery: mapped room ids not found: %s (renamed/removed?)", wanted - seen)
    log.info("discovery: %d rooms, open to %s", len(seen), open_days[-1] if open_days else "-")
    return nights, extras
