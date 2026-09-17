"""
Weekly KTP competitor rate check.

  python run.py                    full run (collect, compare, write reports, email)
  python run.py --end 2027-03-31   shorter window
  python run.py --only ktp,nrma    just some parks
  python run.py --browser          fetch everything through a real browser
  python run.py --no-email         skip the email
  python run.py --rebuild          re-render reports from data/latest.json (no fetching)

Exits non-zero if any park it was asked to cover failed or returned no prices,
so GitHub marks the run red instead of silently saving empty data.
"""

import argparse
import glob
import gzip
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import compare
import config
import notify
import report
from scrapers import discovery, ktp, nrma
from scrapers.fetch import Fetcher

log = logging.getLogger("run")
TZ = ZoneInfo("Australia/Sydney")
PARKS = {"ktp": ktp, "discovery": discovery, "nrma": nrma}


def load_mapping():
    with open("mapping.json") as f:
        return json.load(f)


def read_json(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as f:
        return json.load(f)


def previous_snapshot(run_date):
    files = sorted(glob.glob(os.path.join(config.SNAPSHOT_DIR, "*.json.gz")))
    for f in reversed(files):
        if os.path.basename(f)[:10] < run_date:
            snap = read_json(f)
            if "nights" in snap:            # older per-stay snapshots can't be compared
                return snap
    return None


def collect(parks, end, force_browser):
    mapping = load_mapping()
    start = datetime.now(TZ).date() + timedelta(days=1)
    fetcher = Fetcher(force_browser=force_browser)
    nights, extras, failures = [], [], {}
    try:
        for park in parks:
            log.info("== %s ==", park)
            try:
                n, e = PARKS[park].collect(fetcher, mapping, start, end)
            except Exception as ex:          # keep going with the other parks
                log.exception("%s failed", park)
                failures[park] = str(ex)[:300]
                continue
            priced = sum(1 for x in n if x["rate"] is not None)
            log.info("%s: %d nights, %d priced, %d extras samples", park, len(n), priced, len(e))
            if priced == 0:
                failures[park] = "no prices returned"
            nights.extend(n)
            extras.extend(e)
    finally:
        log.info("requests: %d; browser mode used for: %s", fetcher.calls,
                 ", ".join(sorted(fetcher.browser_sites)) or "none")
        fetcher.close()
    return {
        "run_date": datetime.now(TZ).date().isoformat(),
        "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "parks": list(parks),
        "failures": failures,
        "browser_mode": sorted(fetcher.browser_sites),
        "nights": nights,
        "extras": extras,
    }


def build_context(snap, prev):
    mapping = load_mapping()
    mapping["competitors"] = {k: v for k, v in mapping["competitors"].items() if k in snap["parks"]}
    start = date.fromisoformat(snap["window"]["start"])
    end = date.fromisoformat(snap["window"]["end"])
    rows = compare.build_days(snap["nights"], mapping, start, end)
    cov = compare.coverage(snap["nights"], mapping, start, end)
    last = max([v["priced_to"] for k, v in cov.items() if not k.startswith("_") and v["priced_to"]],
               default=None)
    rows = [r for r in rows if last and r["date"] <= last]      # drop months nobody has priced yet
    counts = {}
    for n in snap["nights"]:
        if n["rate"] is not None:
            counts[n["park"]] = counts.get(n["park"], 0) + 1
    return {
        "mapping": mapping,
        "run_date": snap["run_date"],
        "run_date_nice": date.fromisoformat(snap["run_date"]).strftime("%-d %b %Y"),
        "generated_at": snap.get("generated_at"),
        "window": snap["window"],
        "prev_date": prev["run_date"] if prev else None,
        "rows": rows,
        "actions": compare.actions(rows, mapping),
        "months": compare.month_summary(rows, mapping),
        "coverage": cov,
        "extras": compare.extras_table(snap.get("extras", []), mapping),
        "moves": compare.price_moves(snap["nights"], prev["nights"] if prev else [], mapping),
        "failures": snap["failures"],
        "counts": counts,
        "note": snap.get("note"),
    }


def write_outputs(snap, ctx, save_snapshot=True):
    os.makedirs(config.SNAPSHOT_DIR, exist_ok=True)
    os.makedirs(config.REPORT_DIR, exist_ok=True)
    if save_snapshot:
        with gzip.open(os.path.join(config.SNAPSHOT_DIR, f"{snap['run_date']}.json.gz"), "wt") as f:
            json.dump(snap, f, separators=(",", ":"))
        with gzip.open(os.path.join(config.DATA_DIR, "latest.json.gz"), "wt") as f:
            json.dump(snap, f, separators=(",", ":"))
        old = os.path.join(config.DATA_DIR, "latest.json")
        if os.path.exists(old):
            os.remove(old)
    dash = report.dashboard_html(ctx)
    csv_text = report.csv_text(ctx)
    with open(os.path.join(config.REPORT_DIR, "latest.html"), "w") as f:
        f.write(dash)
    with open(os.path.join(config.REPORT_DIR, "latest.csv"), "w", newline="") as f:
        f.write(csv_text)
    summary_md = report.markdown(ctx)
    with open(os.path.join(config.REPORT_DIR, "summary.md"), "w") as f:
        f.write(summary_md + "\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(summary_md + "\n")
    return dash, csv_text, summary_md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", default=config.END_DATE.isoformat())
    ap.add_argument("--only", default=",".join(PARKS))
    ap.add_argument("--browser", action="store_true")
    ap.add_argument("--no-email", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.rebuild:
        snap = read_json(os.path.join(config.DATA_DIR, "latest.json.gz"))
    else:
        parks = [p.strip() for p in args.only.split(",") if p.strip() in PARKS]
        snap = collect(parks, date.fromisoformat(args.end), args.browser)

    prev = previous_snapshot(snap["run_date"])
    ctx = build_context(snap, prev)
    has_data = any(ctx["counts"].values())
    dash, csv_text, summary_md = write_outputs(snap, ctx, save_snapshot=has_data and not args.rebuild)
    print(summary_md)

    if not args.no_email and not args.rebuild:
        bad = f" – DATA MISSING ({', '.join(snap['failures'])})" if snap["failures"] else ""
        subject = f"KTP competitor rates – {ctx['run_date_nice']}{bad}"
        try:
            notify.send(subject, report.email_html(ctx), summary_md, [
                (f"ktp-competitor-rates-{snap['run_date']}.html", dash.encode(), "text", "html"),
                (f"ktp-competitor-rates-{snap['run_date']}.csv", csv_text.encode(), "text", "csv"),
            ])
        except Exception:
            log.exception("Email failed")
            snap["failures"]["email"] = "send failed"

    if snap["failures"]:
        log.error("Finished with problems: %s", snap["failures"])
        sys.exit(1)


if __name__ == "__main__":
    main()
