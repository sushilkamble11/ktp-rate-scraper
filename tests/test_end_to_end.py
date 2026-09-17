import os
import shutil
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import compare  # noqa: E402
import report  # noqa: E402
import run  # noqa: E402
from tests.fake_sites import FakeFetcher  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(monkeypatch, tmp_path, bump=1.0, end=date(2028, 12, 31)):
    monkeypatch.setattr(run, "Fetcher", lambda **kw: FakeFetcher(bump))
    return run.collect(("ktp", "discovery", "nrma"), end, False)


def test_pipeline(tmp_path, monkeypatch):
    shutil.copy(os.path.join(REPO, "mapping.json"), tmp_path)
    monkeypatch.chdir(tmp_path)
    snap = _run(monkeypatch, tmp_path)
    assert not snap["failures"]
    ctx = run.build_context(snap, None)
    run.write_outputs(snap, ctx)
    for f in ("reports/latest.html", "reports/latest.csv", "data/latest.json.gz"):
        assert os.path.exists(f)

    cov = ctx["coverage"]
    assert cov["ktp"]["priced_to"] == "2027-05-31"
    assert cov["nrma"]["priced_to"] == "2028-03-31" and cov["nrma"]["open_to"] == "2027-10-31"
    assert max(r["date"] for r in ctx["rows"]) == "2028-03-31"      # nothing priced beyond

    assert ctx["actions"], "expected some raise/lower suggestions"
    for a in ctx["actions"]:
        assert a["cat"] != "3br"                                   # no-equivalent never flagged
        assert (a["suggest"] > a["ktp"]) if a["action"] == "raise" else (a["suggest"] < a["ktp"])

    guide = [m for m in ctx["months"] if m["ktp_open"] == 0 and m["weeknight"]["market"]]
    assert guide and all(m["month"] >= "2027-06" for m in guide)

    ex = {e["cat"]: e for e in ctx["extras"]}
    assert ex["2br"]["ktp"]["adult"] == 35 and ex["2br"]["discovery"]["child"] == 20
    assert ex["cedar"]["nrma"]["adult"] == 25 and ex["unpowered"]["nrma"]["child"] == 10

    html = open("reports/latest.html").read()
    assert "<title>KTP Rate Desk</title>" in html and "/*__DATA__*/" not in html
    assert report.dashboard_html(ctx, standalone=False).startswith("<title>")

    # a week later competitors are 20% dearer -> moves are reported
    snap2 = _run(monkeypatch, tmp_path, bump=1.2)
    moves = compare.price_moves(snap2["nights"], snap["nights"], ctx["mapping"])
    assert moves and all(m["direction"] == "up" for m in moves)
    snap2["run_date"] = "2999-01-01"
    assert run.build_context(snap2, snap)["prev_date"] == snap["run_date"]
    assert "Room to raise" in report.email_html(ctx)


def test_action_rules():
    row = {"gap": -12, "sold_out": []}
    assert compare.action_for(row, 100) == "raise"
    assert compare.action_for({"gap": -6, "sold_out": ["nrma"]}, 100) == "raise"
    assert compare.action_for({"gap": -6, "sold_out": []}, 100) is None
    assert compare.action_for({"gap": 16, "sold_out": []}, 100) == "lower"
    assert compare.action_for({"gap": 16, "sold_out": ["nrma"]}, 100) is None
    assert compare.action_for({"gap": -30, "sold_out": []}, None) is None
    # between the competitors -> no call
    assert compare.action_for({"gap": -20, "sold_out": [], "low": 90, "high": 160}, 100) is None
    assert compare.action_for({"gap": 20, "sold_out": [], "low": 60, "high": 130}, 100) is None
    assert compare.action_for({"gap": -20, "sold_out": [], "low": 110, "high": 140}, 100) == "raise"
    assert compare._date_spans(["2026-12-04", "2026-12-05", "2026-12-11"]) == [
        ("2026-12-04", "2026-12-05"), ("2026-12-11", "2026-12-11")]
