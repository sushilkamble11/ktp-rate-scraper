import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers import discovery, ktp, nrma  # noqa: E402
from scrapers.common import first_weeknights  # noqa: E402

FX = os.path.join(os.path.dirname(__file__), "fixtures")


def load(name):
    with open(os.path.join(FX, name)) as f:
        return json.load(f)


def test_ktp_calendar_statuses_and_min_stay():
    cal = ktp.parse_range(load("ktp_calendar.json"))
    assert ktp.status_of(cal["2026-12-17"]) == "open"
    assert ktp.status_of(cal["2026-12-18"]) == "min stay"
    assert ktp.status_of(cal["2026-11-25"]) == "sold out"
    assert ktp.status_of(cal["2027-07-01"]) == "not open"
    assert ktp.status_of(None) == "not open"
    ds = [date(2026, 12, 17), date(2026, 12, 18), date(2026, 11, 25), date(2027, 7, 1)]
    n = {x["date"]: x for x in ktp.build_nights("263658", "2BR Up", ds, cal, {"2026-12-18": 250.0})}
    assert n["2026-12-17"]["rate"] == 199 and n["2026-12-17"]["units"] == 5
    assert n["2026-12-18"]["rate"] == 250 and n["2026-12-18"]["min_stay"] == 2
    assert n["2026-11-25"]["rate"] is None and n["2027-07-01"]["status"] == "not open"


def test_discovery_calendar_member_rate():
    ns = discovery.parse_calendar(load("discovery_calendar.json"), date(2026, 12, 17), date(2026, 12, 18))
    by = {(x["room_id"], x["date"]): x for x in ns}
    a = by[("NJIN-49-530-RT", "2026-12-17")]
    assert a["rate"] == 180 and a["rack"] == 200 and a["status"] == "open"
    assert by[("NJIN-49-530-RT", "2026-12-18")]["rate"] == 550          # 10% capped at $50
    assert by[("NJIN-49-1822-RT", "2026-12-17")]["status"] == "sold out"
    assert by[("NJIN-49-1822-RT", "2026-12-18")]["status"] == "not open"


def test_discovery_extras():
    ex = discovery.parse_extras(load("discovery_3a1c.json"), 2)
    assert ex["NJIN-49-1822-RT"] == (25, 20) and ex["NJIN-49-2178-RT"] == (15, 10)


def test_nrma_range_member_ratio_and_units():
    ns = {x["date"]: x for x in nrma.parse_range(load("nrma_range.json")) if x["room_id"] == "2"}
    assert ns["2026-12-17"]["rate"] == 162 and ns["2026-12-17"]["rack"] == 180
    assert ns["2026-12-17"]["status"] == "open" and ns["2026-12-17"]["units"] == 2
    assert ns["2026-12-18"]["status"] == "sold out"


def test_nrma_member_cap():
    assert nrma.member(180) == 162 and nrma.member(755) == 695 and nrma.member(None) is None


def test_nrma_rates_loaded_but_not_bookable():
    data = load("nrma_range.json")
    for a in data["Accommodation"]:
        a["Availability"] = {"2026-12-17": 0, "2026-12-18": 0}
    ns = nrma.parse_range(data)
    assert {x["status"] for x in ns} == {"not bookable"}
    assert all(x["rate"] for x in ns)


def test_placeholder_rates_are_not_prices():
    data = load("nrma_range.json")
    data["Accommodation"][0]["Pricing"][0]["RatePerDay"][1]["2026-12-18"]["Amount"] = 9999
    ns = {(x["room_id"], x["date"]): x for x in nrma.parse_range(data)}
    assert ns[("2", "2026-12-18")]["rate"] is None and ns[("2", "2026-12-18")]["status"] == "not open"


def test_first_weeknights():
    ds = [date(2026, 10, 2), date(2026, 10, 3), date(2026, 10, 4), date(2026, 11, 6), date(2026, 11, 9)]
    assert first_weeknights(ds) == {"2026-10": date(2026, 10, 4), "2026-11": date(2026, 11, 9)}
