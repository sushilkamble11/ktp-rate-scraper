import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers import discovery, ktp, nrma  # noqa: E402

FX = os.path.join(os.path.dirname(__file__), "fixtures")


def load(name):
    with open(os.path.join(FX, name)) as f:
        return json.load(f)


def test_ktp_calendar_weekend_and_extras():
    cal = ktp.parse_range(load("ktp_range.json"))
    assert cal["2026-10-19"]["price"] == 199
    assert cal["2026-12-18"]["min_stay"] == 2
    cal["2026-11-25"] = {"price": 0, "units": 0, "can_check_in": False,
                         "constraint": "sold-out-constraint", "min_stay": 1}
    wk = {"2026-12-18": {"price": 500, "units": 3, "can_check_in": True, "constraint": None, "min_stay": 1},
          "2026-10-23": {"price": 358.2, "units": 3, "can_check_in": True, "constraint": None, "min_stay": 1}}
    picks = ktp.extras_probe_dates(date(2026, 10, 19), 61, cal)
    assert picks[date(2026, 10, 18)] == date(2026, 10, 19)          # Monday of that week
    extras = {ktp.week_key(date(2026, 10, 19)): (35, 35)}
    recs = ktp.build_records("263658", "2BR Up", date(2026, 10, 19), 61, cal, wk, extras)
    by = {(r["stay"], r["check_in"]): r for r in recs}
    n = by[("night", "2026-10-19")]
    assert n["price"] == 199 and n["bookable"] and n["extra_adult"] == 35
    assert by[("night", "2026-10-23")]["extra_child"] == 35            # same week
    assert by[("night", "2026-10-26")]["extra_adult"] == 35            # unprobed week borrows nearest
    dec = by[("night", "2026-12-18")]
    assert not dec["bookable"] and dec["note"] == "min 2 nights"
    assert dec["estimated"] and dec["price"] == 250
    w = by[("weekend", "2026-10-23")]
    assert w["price"] == 358.2 and w["nights"] == 2 and w["bookable"]
    assert by[("night", "2026-11-25")]["note"] == "sold out"
    assert by[("night", "2026-10-20")]["note"] == "no data"
    assert ktp.week_key(date(2026, 10, 18)) == date(2026, 10, 18)     # Sunday maps to itself


def test_discovery_member_price_and_extras():
    recs = discovery.parse(load("discovery_3a1c.json"), date(2026, 10, 16), 2, "weekend")
    r = recs["NJIN-49-1822-RT"]
    assert r["price"] == 448.2 and r["rack"] == 498 and r["bookable"]
    ex = discovery.parse_extras(load("discovery_3a1c.json"), 2)
    assert ex["NJIN-49-1822-RT"] == (25, 20)
    assert ex["NJIN-49-2178-RT"] == (15, 10)


def test_discovery_min_stay_estimate():
    recs = discovery.parse(load("discovery_minstay.json"), date(2026, 12, 18), 1, "night")
    r = recs["NJIN-49-530-RT"]
    assert not r["bookable"] and r["note"] == "min 3 nights"
    assert r["estimated"] and r["rack"] == 264 and abs(r["price"] - 237.6) < 0.01
    s = recs["NJIN-49-534-RT"]
    assert s["note"] == "sold out" and s["price"] is None


def test_nrma_standard_rate_codes():
    recs = nrma.parse(load("nrma_1night.json"))
    assert recs["2"]["price"] == 186.3 and recs["2"]["rack"] == 207 and recs["2"]["bookable"]
    assert recs["16"]["note"] == "sold out" and not recs["16"]["bookable"]
    assert recs["5"]["note"] == "min stay not met" and recs["5"]["price"] == 112.5
