"""Line KTP up against each competitor's mapped room and summarise."""

from collections import defaultdict
from datetime import date
from statistics import median

import config

SEGMENTS = {
    "weeknight": "Weeknights (Sun-Thu, 1 night)",
    "weekend": "Weekends (Fri-Sun, 2 nights)",
}


def segment(stay, check_in):
    if stay == "weekend":
        return "weekend"
    dow = date.fromisoformat(check_in).weekday()   # Mon=0 .. Sun=6
    return "weeknight" if dow in (6, 0, 1, 2, 3) else None   # Fri/Sat single nights: detail only


def verdict(pct, band=config.IN_LINE_BAND_PCT):
    if pct is None:
        return "n/a"
    if pct > band:
        return "dearer"
    if pct < -band:
        return "cheaper"
    return "in line"


def _pct(a, b):
    return None if a is None or b in (None, 0) else (a - b) / b * 100


def _r(x, n=1):
    return None if x is None else round(x, n)


def build_rows(records, mapping):
    idx = {(r["park"], r["room_id"], r["stay"], r["check_in"]): r for r in records}
    comps = list(mapping["competitors"])
    rows = []
    for cat in mapping["categories"]:
        ktp = sorted((r for r in records if r["park"] == "ktp" and r["room_id"] == cat["ktp_room_id"]),
                     key=lambda r: (r["check_in"], r["stay"]))
        for k in ktp:
            row = {
                "cat": cat["key"], "label": cat["label"], "stay": k["stay"],
                "check_in": k["check_in"], "nights": k["nights"],
                "dow": date.fromisoformat(k["check_in"]).strftime("%a"),
                "month": k["check_in"][:7],
                "segment": segment(k["stay"], k["check_in"]),
                "ktp": {f: k[f] for f in ("price", "rack", "bookable", "note", "estimated",
                                          "extra_adult", "extra_child", "units_left")},
                "comps": {},
            }
            for comp in comps:
                m = cat["competitors"].get(comp) or {}
                c = idx.get((comp, m.get("room_id"), k["stay"], k["check_in"])) if m.get("room_id") else None
                cp = c["price"] if c else None
                row["comps"][comp] = {
                    "match": m.get("match", "none"),
                    "room": m.get("name"),
                    "price": cp,
                    "rack": c["rack"] if c else None,
                    "bookable": c["bookable"] if c else False,
                    "note": (c["note"] if c else "no data"),
                    "estimated": c["estimated"] if c else False,
                    "extra_adult": c["extra_adult"] if c else None,
                    "extra_child": c["extra_child"] if c else None,
                    "diff": _r(k["price"] - cp, 2) if k["price"] is not None and cp is not None else None,
                    "pct": _r(_pct(k["price"], cp)),
                }
            rows.append(row)
    return rows


def _stats(pairs, nights):
    """pairs = [(ktp_price, comp_price)] for one segment."""
    if not pairs:
        return None
    ka = sum(p[0] for p in pairs) / len(pairs) / nights
    ca = sum(p[1] for p in pairs) / len(pairs) / nights
    pcts = [_pct(a, b) for a, b in pairs]
    pct = _pct(ka, ca)
    return {
        "n": len(pairs),
        "ktp_avg_night": _r(ka, 0), "comp_avg_night": _r(ca, 0),
        "diff_night": _r(ka - ca, 0), "pct": _r(pct), "median_pct": _r(median(pcts)),
        "cheaper": sum(1 for x in pcts if x < -config.IN_LINE_BAND_PCT),
        "dearer": sum(1 for x in pcts if x > config.IN_LINE_BAND_PCT),
        "verdict": verdict(pct),
    }


def summarise(rows, mapping):
    comps = list(mapping["competitors"])
    summary, monthly = [], []
    for cat in mapping["categories"]:
        crows = [r for r in rows if r["cat"] == cat["key"]]
        for comp in comps:
            m = cat["competitors"].get(comp) or {}
            entry = {"cat": cat["key"], "label": cat["label"], "comp": comp,
                     "room": m.get("name"), "match": m.get("match", "none"),
                     "note": m.get("note", ""), "segments": {}}
            by_month = defaultdict(list)
            for seg, nights in (("weeknight", 1), ("weekend", 2)):
                pairs = [(r["ktp"]["price"], r["comps"][comp]["price"]) for r in crows
                         if r["segment"] == seg and r["ktp"]["price"] is not None
                         and r["comps"][comp]["price"] is not None]
                entry["segments"][seg] = _stats(pairs, nights)
                for r in crows:
                    if r["segment"] == seg and r["ktp"]["price"] is not None \
                            and r["comps"][comp]["price"] is not None:
                        by_month[(r["month"], seg)].append((r["ktp"]["price"], r["comps"][comp]["price"]))
            summary.append(entry)
            for (month, seg), pairs in sorted(by_month.items()):
                st = _stats(pairs, 1 if seg == "weeknight" else 2)
                monthly.append({"cat": cat["key"], "comp": comp, "month": month, "segment": seg,
                                "match": entry["match"], **st})
    return summary, monthly


def _med(vals):
    vals = [v for v in vals if v is not None]
    return _r(median(vals), 0) if vals else None


def extras_table(rows, mapping):
    comps = list(mapping["competitors"])
    out = []
    for cat in mapping["categories"]:
        crows = [r for r in rows if r["cat"] == cat["key"] and r["stay"] == "night"]
        e = {"cat": cat["key"], "label": cat["label"],
             "ktp": {"adult": _med(r["ktp"]["extra_adult"] for r in crows),
                     "child": _med(r["ktp"]["extra_child"] for r in crows)}}
        for comp in comps:
            e[comp] = {"room": cat["competitors"].get(comp, {}).get("name"),
                       "adult": _med(r["comps"][comp]["extra_adult"] for r in crows),
                       "child": _med(r["comps"][comp]["extra_child"] for r in crows)}
        out.append(e)
    return out


def price_moves(records, prev_records, mapping):
    """Competitor price changes on mapped rooms since the last snapshot."""
    if not prev_records:
        return []
    mapped = {}
    for cat in mapping["categories"]:
        for comp, m in cat["competitors"].items():
            if m.get("room_id") and m.get("match") != "none":
                mapped.setdefault((comp, m["room_id"]), m["name"])
    prev = {(r["park"], r["room_id"], r["stay"], r["check_in"]): r for r in prev_records}
    moves = []
    for r in records:
        key = (r["park"], r["room_id"])
        if key not in mapped or r["price"] is None or r["estimated"]:
            continue
        p = prev.get((r["park"], r["room_id"], r["stay"], r["check_in"]))
        if not p or p["price"] is None or p.get("estimated"):
            continue
        d = r["price"] - p["price"]
        pct = _pct(r["price"], p["price"])
        if abs(d) >= config.MOVE_MIN_DOLLARS and abs(pct) >= config.MOVE_MIN_PCT:
            moves.append({"park": r["park"], "room": mapped[key], "stay": r["stay"],
                          "check_in": r["check_in"], "was": p["price"], "now": r["price"],
                          "diff": _r(d, 2), "pct": _r(pct)})
    moves.sort(key=lambda m: -abs(m["diff"]))
    return moves


def headline(summary):
    """Per competitor: how many (scored category x segment) KTP is cheaper / in line / dearer."""
    out = {}
    for s in summary:
        if s["match"] == "none":
            continue
        h = out.setdefault(s["comp"], {"cheaper": 0, "in line": 0, "dearer": 0})
        for seg in s["segments"].values():
            if seg:
                h[seg["verdict"]] += 1
    return out
