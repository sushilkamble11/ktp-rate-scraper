"""
NRMA Jindabyne Holiday Park (Newbook, via NRMA's own site API).

GET {BASE}/api/accommodation/get-availability-pricing/
    ?from=..&to=..&promoCode=&adults=..&children=..&infants=0&pets=0&parkName=..
with header x-nb-api-key - exactly what their book-now page sends.

A date range (up to ~3 months) returns, per category, the "Standard Rate"
(flexible) plan with a price for every night (RatePerDay) plus Total and
MemberTotal (My NRMA 10% off), and units available per night.
NRMA loads prices further out than it takes bookings: nights after the last
bookable night are marked "not bookable" but their rates are kept.

Extras: NRMA doesn't itemise them, so one weeknight a month is priced at
3 adults and at 2 adults + 1 child and compared with 2 adults.
"""

import logging
from datetime import date, timedelta
from urllib.parse import quote_plus

import config
from .common import chunks, extra, first_weeknights, night

log = logging.getLogger(__name__)
PARK = "nrma"
HEADERS = {"x-nb-api-key": config.NRMA_API_KEY}


def _url(frm, to_excl, adults, children):
    return (f"{config.NRMA_BASE}/api/accommodation/get-availability-pricing/"
            f"?from={frm.isoformat()}&to={to_excl.isoformat()}&promoCode="
            f"&adults={adults}&children={children}&infants=0&pets=0"
            f"&parkName={quote_plus(config.NRMA_PARK_NAME)}")


def _standard(acc):
    plans = acc.get("Pricing") or []
    for p in plans:
        if "standard" in (p.get("Label") or "").lower():
            return p
    return plans[0] if plans else None


def parse_range(payload):
    """-> list of night records for the range."""
    accs = (payload or {}).get("Accommodation") or []
    # NRMA loads rates before it opens them for booking. Nights after the last
    # night anything at all can be booked are "not bookable yet" (rate kept).
    bookable = [d for a in accs for d, v in (a.get("Availability") or {}).items() if v]
    last_bookable = max(bookable) if bookable else ""
    out = []
    for acc in accs:
        p = _standard(acc)
        if not p:
            continue
        per_day = {}
        for item in p.get("RatePerDay") or []:
            for d, v in item.items():
                per_day[d] = float(v.get("Amount") or 0)
        total, mem = float(p.get("Total") or 0), float(p.get("MemberTotal") or 0)
        ratio = mem / total if total and mem else 1.0
        units = acc.get("Availability") or {}
        for d, amt in sorted(per_day.items()):
            u = units.get(d)
            if not amt:
                st = "not open"
            elif d > last_bookable:
                st = "not bookable"
            elif u == 0:
                st = "sold out"
            else:
                st = "open"
            out.append(night(PARK, acc["Id"], acc.get("Name", ""), date.fromisoformat(d),
                             rate=amt * ratio if amt else None, rack=amt or None,
                             units=u, status=st))
    return out


def totals(payload):
    out = {}
    for acc in (payload or {}).get("Accommodation") or []:
        p = _standard(acc)
        if p and p.get("Total") is not None:
            out[str(acc["Id"])] = float(p["Total"])
    return out


def collect(fetcher, mapping, start: date, end: date):
    get = lambda url: fetcher.get_json(PARK, config.NRMA_PAGE, url, HEADERS)
    nights = []
    for frm, to in chunks(start, end, config.NRMA_RANGE_DAYS):
        got = parse_range(get(_url(frm, to + timedelta(days=1), config.ADULTS, 0)))
        nights.extend(got)
        if not got and frm > start + timedelta(days=300):
            # A range that runs past NRMA's last loaded night comes back empty,
            # so pick up the tail a week at a time, then stop.
            for wf, wt in chunks(frm, to, 7):
                part = parse_range(get(_url(wf, wt + timedelta(days=1), config.ADULTS, 0)))
                if not part:
                    break
                nights.extend(part)
            break
    wanted = {c["competitors"][PARK]["room_id"] for c in mapping["categories"]
              if c["competitors"].get(PARK, {}).get("room_id")}
    open_days = sorted({date.fromisoformat(n["date"]) for n in nights
                        if n["status"] == "open" and n["room_id"] in wanted})
    extras = []
    for month, d in first_weeknights(open_days).items():
        nxt = d + timedelta(days=1)
        base, pa, pc = (totals(get(_url(d, nxt, a, c))) for a, c in ((2, 0), (3, 0), (2, 1)))
        for rid, b in base.items():
            extras.append(extra(PARK, rid, month,
                                pa[rid] - b if rid in pa else None,
                                pc[rid] - b if rid in pc else None))
    seen = {n["room_id"] for n in nights}
    if wanted - seen:
        log.warning("nrma: mapped room ids not found: %s (renamed/removed?)", wanted - seen)
    log.info("nrma: %d nights, open to %s", len(nights), open_days[-1] if open_days else "-")
    return nights, extras
