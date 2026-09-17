"""Line KTP up against the market night by night, then turn the gaps into
actions, monthly summaries and an opening-rate guide."""

from collections import defaultdict
from datetime import date
from statistics import mean, median

import config

SCORED = ("exact", "close")


def is_weekend(iso):
    return date.fromisoformat(iso).weekday() in (4, 5)      # Fri & Sat nights


def pct(a, b):
    return None if a is None or not b else (a - b) / b * 100


def r0(x):
    return None if x is None else round(x)


def r1(x):
    return None if x is None else round(x, 1)


def round_to(x, step=config.ROUND_TO):
    return None if x is None else int(step * round(x / step))


def build_days(nights, mapping, start, end):
    """One row per category per night."""
    idx = {(n["park"], n["room_id"], n["date"]): n for n in nights}
    comps = list(mapping["competitors"])
    rows = []
    for cat in mapping["categories"]:
        for d in _dates(start, end):
            k = idx.get(("ktp", cat["ktp_room_id"], d))
            row = {"cat": cat["key"], "date": d, "month": d[:7], "weekend": is_weekend(d),
                   "ktp": {"rate": k["rate"] if k else None,
                           "status": k["status"] if k else "not open",
                           "units": k["units"] if k else None,
                           "min_stay": k["min_stay"] if k else None},
                   "comps": {}}
            market_rates, sold_out = [], []
            for comp in comps:
                m = cat["competitors"].get(comp) or {}
                n = idx.get((comp, m.get("room_id"), d)) if m.get("room_id") else None
                rate = n["rate"] if n and n["status"] != "not open" else None
                st = n["status"] if n else "not open"
                row["comps"][comp] = {"rate": rate, "status": st, "match": m.get("match", "none")}
                if rate is not None and m.get("match") in SCORED:
                    market_rates.append(rate)
                    if st == "sold out":
                        sold_out.append(comp)
            row["market"] = mean(market_rates) if market_rates else None
            row["low"] = min(market_rates) if market_rates else None
            row["high"] = max(market_rates) if market_rates else None
            row["sold_out"] = sold_out
            kr = row["ktp"]["rate"] if row["ktp"]["status"] in ("open", "min stay") else None
            row["gap"] = pct(kr, row["market"])
            row["action"] = action_for(row, kr)
            rows.append(row)
    return rows


def _dates(start, end):
    d = start
    while d <= end:
        yield d.isoformat()
        d = date.fromordinal(d.toordinal() + 1)


def action_for(row, ktp_rate):
    """raise: we're the cheapest and well under the market average (or a
    competitor is full and we're under). lower: we're the dearest and well over.
    When we sit between the competitors the call isn't clear, so no flag."""
    g = row["gap"]
    if g is None or ktp_rate is None:
        return None
    cheapest = row.get("low") is None or ktp_rate < row["low"]
    dearest = row.get("high") is None or ktp_rate > row["high"]
    if cheapest and g <= -config.RAISE_GAP_PCT:
        return "raise"
    if row["sold_out"] and g <= -config.IN_LINE_BAND_PCT:
        return "raise"            # a competitor is full and we're under the market
    if dearest and g >= config.LOWER_GAP_PCT and not row["sold_out"]:
        return "lower"
    return None


def _date_spans(isos):
    """['2026-12-04','2026-12-05','2026-12-11'] -> [('2026-12-04','2026-12-05'), ('2026-12-11','2026-12-11')]"""
    spans, cur = [], None
    for d in sorted(isos):
        o = date.fromisoformat(d).toordinal()
        if cur and o == cur[2] + 1:
            cur = (cur[0], d, o)
        else:
            if cur:
                spans.append((cur[0], cur[1]))
            cur = (d, d, o)
    if cur:
        spans.append((cur[0], cur[1]))
    return spans


def actions(rows, mapping):
    """Group nightly actions by category, month, action and weekday/weekend."""
    labels = {c["key"]: c["label"] for c in mapping["categories"]}
    groups = defaultdict(list)
    for r in rows:
        if r["action"]:
            groups[(r["cat"], r["month"], r["action"], r["weekend"])].append(r)
    out = []
    for (cat, month, act, wkend), rs in groups.items():
        ktp = median(x["ktp"]["rate"] for x in rs)
        market = median(x["market"] for x in rs)
        suggest = round_to(market)
        if act == "raise" and suggest <= ktp:
            suggest = round_to(ktp * 1.05) if round_to(ktp * 1.05) > ktp else ktp + config.ROUND_TO
        if act == "lower" and suggest >= ktp:
            continue
        per_comp = {}
        for comp in mapping["competitors"]:
            vals = [x["comps"][comp]["rate"] for x in rs if x["comps"][comp]["rate"] is not None
                    and x["comps"][comp]["match"] in SCORED]
            per_comp[comp] = r0(median(vals)) if vals else None
        sold = sorted({c for x in rs for c in x["sold_out"]})
        out.append({
            "cat": cat, "label": labels[cat], "month": month, "action": act,
            "weekend": wkend, "nights": len(rs),
            "spans": _date_spans([x["date"] for x in rs]),
            "ktp": r0(ktp), "market": r0(market), "suggest": suggest,
            "gap": r1(pct(ktp, market)), "comps": per_comp, "sold_out": sold,
            "value": r0(abs(suggest - ktp) * len(rs)),
        })
    out.sort(key=lambda a: (-a["value"], a["month"]))
    return out


def month_summary(rows, mapping):
    comps = list(mapping["competitors"])
    by = defaultdict(list)
    for r in rows:
        by[(r["month"], r["cat"])].append(r)
    out = []
    for (month, cat), rs in sorted(by.items()):
        entry = {"month": month, "cat": cat}
        for part, sel in (("weeknight", False), ("weekend", True)):
            ps = [r for r in rs if r["weekend"] == sel]
            k = [r["ktp"]["rate"] for r in ps if r["ktp"]["rate"] is not None
                 and r["ktp"]["status"] in ("open", "min stay")]
            m = [r["market"] for r in ps if r["market"] is not None]
            e = {"ktp": r0(mean(k)) if k else None, "market": r0(mean(m)) if m else None}
            for c in comps:
                v = [r["comps"][c]["rate"] for r in ps if r["comps"][c]["rate"] is not None]
                e[c] = r0(mean(v)) if v else None
            e["gap"] = r1(pct(e["ktp"], e["market"]))
            e["suggest"] = round_to(median(m)) if m else None
            entry[part] = e
        entry["ktp_open"] = sum(1 for r in rs if r["ktp"]["status"] in ("open", "min stay"))
        entry["ktp_sold_out"] = sum(1 for r in rs if r["ktp"]["status"] == "sold out")
        entry["raise"] = sum(1 for r in rs if r["action"] == "raise")
        entry["lower"] = sum(1 for r in rs if r["action"] == "lower")
        out.append(entry)
    return out


def coverage(nights, mapping, start, end):
    """How far ahead each park has prices / takes bookings (mapped rooms only)."""
    wanted = {"ktp": {c["ktp_room_id"] for c in mapping["categories"]}}
    for comp in mapping["competitors"]:
        wanted[comp] = {c["competitors"][comp]["room_id"] for c in mapping["categories"]
                        if c["competitors"].get(comp, {}).get("room_id")}
    out = {}
    for park, ids in wanted.items():
        ns = [n for n in nights if n["park"] == park and n["room_id"] in ids]
        priced = [n["date"] for n in ns if n["rate"] is not None and n["status"] != "not open"]  # incl. not bookable
        booking = [n["date"] for n in ns if n["status"] in ("open", "min stay")]
        out[park] = {"priced_to": max(priced) if priced else None,
                     "open_to": max(booking) if booking else None,
                     "nights": len(ns)}
    out["_window"] = {"start": start.isoformat(), "end": end.isoformat()}
    return out


def extras_table(extras, mapping):
    def med(vals):
        vals = [v for v in vals if v is not None]
        return r0(median(vals)) if vals else None
    out = []
    for cat in mapping["categories"]:
        e = {"cat": cat["key"], "label": cat["label"]}
        k = [x for x in extras if x["park"] == "ktp" and x["room_id"] == cat["ktp_room_id"]]
        e["ktp"] = {"adult": med(x["adult"] for x in k), "child": med(x["child"] for x in k)}
        for comp in mapping["competitors"]:
            m = cat["competitors"].get(comp) or {}
            xs = [x for x in extras if x["park"] == comp and x["room_id"] == m.get("room_id")]
            e[comp] = {"room": m.get("name"), "adult": med(x["adult"] for x in xs),
                       "child": med(x["child"] for x in xs)}
        out.append(e)
    return out


def price_moves(nights, prev_nights, mapping):
    """Competitor nightly rate changes on mapped rooms since the last snapshot,
    grouped by room and month."""
    if not prev_nights:
        return []
    names = {}
    for cat in mapping["categories"]:
        for comp, m in cat["competitors"].items():
            if m.get("room_id") and m.get("match") in SCORED:
                names[(comp, m["room_id"])] = m["name"]
    prev = {(n["park"], n["room_id"], n["date"]): n for n in prev_nights}
    groups = defaultdict(list)
    for n in nights:
        key = (n["park"], n["room_id"])
        if key not in names or n["rate"] is None or n["status"] == "not open":
            continue
        p = prev.get((n["park"], n["room_id"], n["date"]))
        if not p or p.get("rate") is None or p.get("status") == "not open":
            continue
        d = n["rate"] - p["rate"]
        if abs(d) >= config.MOVE_MIN_DOLLARS and abs(pct(n["rate"], p["rate"])) >= config.MOVE_MIN_PCT:
            groups[(n["park"], n["room_id"], n["date"][:7], d > 0)].append((n["date"], p["rate"], n["rate"]))
    out = []
    for (park, rid, month, up), xs in groups.items():
        out.append({"park": park, "room": names[(park, rid)], "month": month,
                    "direction": "up" if up else "down", "nights": len(xs),
                    "spans": _date_spans([x[0] for x in xs]),
                    "was": r0(median(x[1] for x in xs)), "now": r0(median(x[2] for x in xs))})
    out.sort(key=lambda m: -m["nights"] * abs(m["now"] - m["was"]))
    return out
