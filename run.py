"""
Weekly KTP competitor rate check.

  python run.py                    full run (scrape, compare, write reports, email)
  python run.py --days 7           quick test over 7 days
  python run.py --only ktp,nrma    just some parks
  python run.py --browser          fetch everything through a real browser
  python run.py --no-email         skip the email
  python run.py --rebuild          re-render reports from data/latest.json (no scraping)

Exits non-zero if any park failed or returned no prices, so GitHub marks the
run red instead of silently saving empty data.
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
from scrapers.common import stay_plan
from scrapers.fetch import Fetcher

log = logging.getLogger("run")
TZ = ZoneInfo("Australia/Sydney")
PARKS = ("ktp", "discovery", "nrma")


def load_mapping():
    with open("mapping.json") as f:
        return json.load(f)


def read_snapshot(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as f:
        return json.load(f)


def previous_snapshot(run_date):
    files = sorted(glob.glob(os.path.join(config.SNAPSHOT_DIR, "*.json.gz")))
    older = [f for f in files if os.path.basename(f)[:10] < run_date]
    if not older:
        return None
    return read_snapshot(older[-1])


def scrape(parks, days, force_browser):
    mapping = load_mapping()
    start = datetime.now(TZ).date() + timedelta(days=1)
    plan = stay_plan(start, days)
    fetcher = Fetcher(force_browser=force_browser)
    records, failures = [], {}
    try:
        for park in parks:
            log.info("== %s ==", park)
            try:
                if park == "ktp":
                    recs = ktp.collect(fetcher, mapping, start, days)
                elif park == "discovery":
                    recs = discovery.collect(fetcher, mapping, plan)
                else:
                    recs = nrma.collect(fetcher, mapping, plan)
            except Exception as e:   # keep going with the other parks
                log.exception("%s failed", park)
                failures[park] = str(e)[:300]
                continue
            priced = sum(1 for r in recs if r["price"] is not None)
            log.info("%s: %d records, %d with a price", park, len(recs), priced)
            if priced == 0:
                failures[park] = "no prices returned"
            records.extend(recs)
    finally:
        log.info("HTTP calls: %d; browser mode used for: %s", fetcher.calls,
                 ", ".join(sorted(fetcher.browser_sites)) or "none")
        fetcher.close()
    return {
        "run_date": datetime.now(TZ).date().isoformat(),
        "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "window": {"start": start.isoformat(), "days": days},
        "parks": list(parks),
        "failures": failures,
        "browser_mode": sorted(fetcher.browser_sites),
        "records": records,
    }


def build_context(snap, prev):
    mapping = load_mapping()
    rows = compare.build_rows(snap["records"], mapping)
    summary, monthly = compare.summarise(rows, mapping)
    prev_records = prev["records"] if prev else []
    counts = {}
    for r in snap["records"]:
        if r["price"] is not None:
            counts[r["park"]] = counts.get(r["park"], 0) + 1
    return {
        "mapping": mapping,
        "run_date": snap["run_date"],
        "run_date_nice": date.fromisoformat(snap["run_date"]).strftime("%-d %b %Y"),
        "prev_date": prev["run_date"] if prev else None,
        "rows": rows, "summary": summary, "monthly": monthly,
        "extras": compare.extras_table(rows, mapping),
        "moves": compare.price_moves(snap["records"], prev_records, mapping),
        "headline": compare.headline(summary),
        "failures": snap["failures"],
        "counts": counts,
    }


def write_outputs(snap, ctx, save_snapshot=True):
    os.makedirs(config.SNAPSHOT_DIR, exist_ok=True)
    os.makedirs(config.REPORT_DIR, exist_ok=True)
    if save_snapshot:
        with gzip.open(os.path.join(config.SNAPSHOT_DIR, f"{snap['run_date']}.json.gz"), "wt") as f:
            json.dump(snap, f, separators=(",", ":"))
        with open(os.path.join(config.DATA_DIR, "latest.json"), "w") as f:
            json.dump(snap, f, separators=(",", ":"))
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
    ap.add_argument("--days", type=int, default=config.DAYS_AHEAD)
    ap.add_argument("--only", default=",".join(PARKS))
    ap.add_argument("--browser", action="store_true")
    ap.add_argument("--no-email", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)   # one line per request is too noisy

    if args.rebuild:
        snap = read_snapshot(os.path.join(config.DATA_DIR, "latest.json"))
    else:
        parks = [p.strip() for p in args.only.split(",") if p.strip() in PARKS]
        snap = scrape(parks, args.days, args.browser)

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
