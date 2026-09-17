"""
NRMA Jindabyne Holiday Park (Newbook, via NRMA's own site API).

GET {BASE}/api/accommodation/get-availability-pricing/
    ?from=..&to=..&promoCode=&adults=..&children=..&infants=0&pets=0&parkName=..
with header x-nb-api-key - exactly what their book-now page sends.

Returns every category with its rate plans. We use the "Standard Rate"
(flexible) plan: Total = public price, MemberTotal = My NRMA member price.
Plan Code: 0 = bookable, 6 = stay rule not met (min nights), 3 = too many guests.
StayThrough=false with Code 0 means sold out on at least one night.

Extras: NRMA doesn't itemise them, so we price the same stay at 3 adults and
at 2 adults + 1 child and take the difference - on one weeknight a week,
applied to that week.
"""

import logging
from datetime import timedelta
from urllib.parse import quote_plus

import config
from .common import extras_probe_nights, nearest_week, record, week_key

log = logging.getLogger(__name__)
PARK = "nrma"
HEADERS = {"x-nb-api-key": config.NRMA_API_KEY}
CODE_NOTES = {3: "too many guests", 6: "min stay not met"}


def _url(check_in, nights, adults, children):
    to = check_in + timedelta(days=nights)
    return (f"{config.NRMA_BASE}/api/accommodation/get-availability-pricing/"
            f"?from={check_in.isoformat()}&to={to.isoformat()}&promoCode="
            f"&adults={adults}&children={children}&infants=0&pets=0"
            f"&parkName={quote_plus(config.NRMA_PARK_NAME)}")


def _standard(acc):
    plans = acc.get("Pricing") or []
    for p in plans:
        if "standard" in (p.get("Label") or "").lower():
            return p
    return plans[0] if plans else None


def parse(payload):
    """-> {room_id: dict(name, price, rack, bookable, note, units_left)}"""
    out = {}
    for acc in (payload or {}).get("Accommodation") or []:
        p = _standard(acc)
        if not p:
            continue
        code = int(p.get("Code") or 0)
        stay_ok = bool(acc.get("StayThrough"))
        units = acc.get("SitesAvailable")
        if code == 0 and stay_ok:
            note = ""
        elif code in CODE_NOTES:
            note = CODE_NOTES[code]
        else:
            note = "sold out"
        total = p.get("Total")
        member = p.get("MemberTotal")
        out[str(acc["Id"])] = dict(
            name=acc.get("Name", ""),
            price=member if member else total,
            rack=total,
            bookable=(code == 0 and stay_ok),
            note=note,
            units_left=units,
            estimated=False,
        )
    return out


def totals(payload):
    return {k: v["rack"] for k, v in parse(payload).items()}


def collect(fetcher, mapping, plan):
    wanted = {c["competitors"][PARK]["room_id"] for c in mapping["categories"]
              if c["competitors"].get(PARK, {}).get("room_id")}
    probes = extras_probe_nights(plan)
    rows, extras, seen = [], {}, set()
    for stay, check_in, nights in plan:
        get = lambda a, c: fetcher.get_json(PARK, config.NRMA_PAGE,
                                            _url(check_in, nights, a, c), HEADERS)
        base = parse(get(config.ADULTS, 0))
        seen |= set(base)
        rows.extend((rid, stay, check_in, nights, r) for rid, r in base.items())
        if stay == "night" and check_in in probes:
            plus_a, plus_c = totals(get(3, 0)), totals(get(2, 1))
            for rid, r in base.items():
                if r["rack"] is None:
                    continue
                ea = plus_a[rid] - r["rack"] if plus_a.get(rid) is not None else None
                ec = plus_c[rid] - r["rack"] if plus_c.get(rid) is not None else None
                extras.setdefault(rid, {})[week_key(check_in)] = (ea, ec)
    recs = []
    for rid, stay, check_in, nights, r in rows:
        ea, ec = nearest_week(extras.get(rid, {}), week_key(check_in))
        recs.append(record(PARK, rid, r.pop("name"), stay, check_in, nights,
                           extra_adult=ea, extra_child=ec, **r))
    missing = wanted - seen
    if missing:
        log.warning("nrma: mapped room ids never seen: %s (renamed/removed?)", missing)
    return recs
