import os
import shutil
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import compare  # noqa: E402
import run  # noqa: E402
from tests.fake_sites import FakeFetcher  # noqa: E402


def test_pipeline(tmp_path, monkeypatch):
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    shutil.copy(os.path.join(repo, "mapping.json"), tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run, "Fetcher", lambda **kw: FakeFetcher())
    snap = run.scrape(("ktp", "discovery", "nrma"), 40, False)
    assert not snap["failures"]
    ctx = run.build_context(snap, None)
    run.write_outputs(snap, ctx)
    assert os.path.exists("reports/latest.html") and os.path.exists("reports/latest.csv")
    s = {(x["cat"], x["comp"]): x for x in ctx["summary"]}
    assert s[("2br_upgraded", "discovery")]["segments"]["weeknight"]["n"] > 10
    assert s[("2br_upgraded", "discovery")]["segments"]["weekend"]["n"] >= 5
    assert s[("3br", "nrma")]["match"] == "none"
    assert "3br" not in [k for k, _ in ctx["headline"].items()]
    ex = {e["cat"]: e for e in ctx["extras"]}
    assert ex["2br"]["ktp"]["adult"] == 35 and ex["2br"]["discovery"]["child"] == 20
    assert ex["cedar"]["nrma"]["adult"] == 25 and ex["unpowered"]["nrma"]["child"] == 10

    # second week: competitors put prices up 20% -> moves are reported
    monkeypatch.setattr(run, "Fetcher", lambda **kw: FakeFetcher(bump=1.2))
    snap2 = run.scrape(("ktp", "discovery", "nrma"), 40, False)
    snap2["run_date"] = "2999-01-01"
    moves = compare.price_moves(snap2["records"], snap["records"], ctx["mapping"])
    assert moves and all(m["pct"] > 0 for m in moves)
    ctx2 = run.build_context(snap2, snap)
    assert ctx2["prev_date"] == snap["run_date"]
    import report
    assert "price moves" in report.email_html(ctx2).lower()


def test_segments():
    assert compare.segment("night", "2026-10-18") == "weeknight"   # Sunday
    assert compare.segment("night", "2026-10-23") is None          # Friday
    assert compare.segment("weekend", "2026-10-23") == "weekend"
    assert compare.verdict(6) == "dearer" and compare.verdict(-6) == "cheaper" and compare.verdict(4) == "in line"
