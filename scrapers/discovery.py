"""
Discovery Parks Jindabyne (G'day Group booking API, park code NJIN).

GET {API}/parks/NJIN/availability?checkIn=..&checkOut=..&adults=..&children=..&infants=0
with header Gday-Caller: DhpWeb - the same call their park page makes.

For each stay the response lists every room type as `available` (with a
MemberOffer: baseAmount = public price, totalAmount = member price) or
`unavailable` (sold out / min-stay not met, with minNightsStay when that's why).
Every room type also carries a nightly price calendar, used to estimate a
price when a stay can't be booked as asked (e.g. 1 night on a 3-night-min date).

Extras come from a second call at 3 adults + 1 child (rateBreakdown gives
additionalAdult and additionalChild). They're read on one weeknight a week and
applied to that week, which keeps the request count down.
"""

import logging
from datetime import timedelta

import config
from .common import extras_probe_nights, nearest_week, record, week_key

log = logging.getLogger(__name__)
PARK = "discovery"
MEMBER_PCT = 0.10
MEMBER_CAP = 50.0


def _url(check_in, nights, adults, children):
    co = check_in + timedelta(days=nights)
    return (f"{config.DISCOVERY_API}/parks/{config.DISCOVERY_PARK_CODE}/availability"
            f"?checkIn={check_in.isoformat()}&checkOut={co.isoformat()}"
            f"&adults={adults}&children={children}&infants=0")


HEADERS = {"Gday-Caller": config.DISCOVERY_CALLER}


def _member_offer(room):
    offers = room.get("offers") or []
    for o in offers:
        if o.get("templateCode") == "MemberOffer":
            return o
    return offers[0] if offers else None


def _calendar_total(room, check_in, nights):
    cal = {a["date"][:10]: a for a in room.get("availability") or []}
    total = 0.0
    for i in range(nights):
        a = cal.get((check_in + timedelta(days=i)).isoformat())
        if not a or not a.get("price") or a.get("isAvailable") is False:
            return None
        total += a["price"]
    return total


def parse(payload, check_in, nights, stay):
    """-> {room_code: record-kwargs} for one stay at base occupancy."""
    res = (payload or {}).get("result") or {}
    msgs = " ".join(m.get("message", "") for m in res.get("messages") or [])
    out = {}
    for room in res.get("available") or []:
        o = _member_offer(room)
        if not o:
            continue
        p = o.get("price") or {}
        out[room["code"]] = dict(name=room["name"], price=p.get("totalAmount"),
                                 rack=p.get("baseAmount"), bookable=True, note="",
                                 units_left=room.get("accommodationsAvailable"))
    for room in res.get("unavailable") or []:
        mn = room.get("minNightsStay")
        note = f"min {mn} nights" if mn and mn > nights else "sold out"
        rack = _calendar_total(room, check_in, nights) if mn and mn > nights else None
        price = None if rack is None else rack - min(rack * MEMBER_PCT, MEMBER_CAP)
        out[room["code"]] = dict(name=room["name"], price=price, rack=rack, bookable=False,
                                 note=note, units_left=room.get("accommodationsAvailable"),
                                 estimated=rack is not None)
    if msgs and not out:
        log.info("discovery %s: %s", check_in, msgs)
    return out


def parse_extras(payload, nights):
    """-> {room_code: (extra_adult_per_night, extra_child_per_night)} from a 3A+1C call."""
    res = (payload or {}).get("result") or {}
    out = {}
    for room in res.get("available") or []:
        o = _member_offer(room)
        rb = ((o or {}).get("price") or {}).get("rateBreakdown")
        if rb is None:
            continue
        out[room["code"]] = (rb.get("additionalAdult", 0) / nights,
                             rb.get("additionalChild", 0) / nights)
    return out


def collect(fetcher, mapping, plan):
    wanted = {c["competitors"][PARK]["room_id"] for c in mapping["categories"]
              if c["competitors"].get(PARK, {}).get("room_id")}
    probes = extras_probe_nights(plan)
    rows, extras, seen = [], {}, set()
    for stay, check_in, nights in plan:
        base = parse(fetcher.get_json(PARK, config.DISCOVERY_PAGE,
                                      _url(check_in, nights, config.ADULTS, 0), HEADERS),
                     check_in, nights, stay)
        seen |= set(base)
        rows.extend((code, stay, check_in, nights, r) for code, r in base.items())
        if stay == "night" and check_in in probes:
            ex = parse_extras(fetcher.get_json(PARK, config.DISCOVERY_PAGE,
                                               _url(check_in, nights, 3, 1), HEADERS), nights)
            for code, v in ex.items():
                extras.setdefault(code, {})[week_key(check_in)] = v
    recs = []
    for code, stay, check_in, nights, r in rows:
        ea, ec = nearest_week(extras.get(code, {}), week_key(check_in))
        recs.append(record(PARK, code, r.pop("name"), stay, check_in, nights,
                           extra_adult=ea, extra_child=ec, **r))
    missing = wanted - seen
    if missing:
        log.warning("discovery: mapped room ids never seen: %s (renamed/removed?)", missing)
    return recs
