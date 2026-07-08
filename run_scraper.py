"""
Runs the Discovery + NRMA scrapers across the configured date range and
writes results to history/latest.json (for the dashboard) and a
timestamped history/<date>.json snapshot.

Usage:
    python run_scraper.py            # full run
    python run_scraper.py --debug    # single date, dumps raw page text
"""

import json
import os
import sys
import time
import traceback
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

import config
from scrapers import discovery, nrma


def load_mapping():
    with open("mapping.json") as f:
        return json.load(f)


def daterange(start: date, end: date):
    d = start
    while d < end:
        yield d
        d += timedelta(days=1)


def run_debug():
    """Scrapes a single (tomorrow's) date and dumps raw text for inspection."""
    os.makedirs("debug_output", exist_ok=True)
    target = date.today() + timedelta(days=1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS)
        page = browser.new_page()

        try:
            page.goto(
                discovery.build_url(target, target + timedelta(days=1),
                                     config.ADULTS, config.CHILDREN, config.INFANTS),
                wait_until="networkidle", timeout=config.PAGE_TIMEOUT_MS,
            )
            page.wait_for_timeout(2000)
            text = page.inner_text("main")
            with open("debug_output/discovery_raw.txt", "w") as f:
                f.write(text)
            print("Wrote debug_output/discovery_raw.txt")
        except Exception:
            print("Discovery debug scrape failed:")
            traceback.print_exc()

        try:
            page.goto(nrma.URL, wait_until="networkidle", timeout=config.PAGE_TIMEOUT_MS)
            nrma._select_date_range(page, target, target + timedelta(days=1))
            page.wait_for_timeout(2000)
            text = page.inner_text("main")
            with open("debug_output/nrma_raw.txt", "w") as f:
                f.write(text)
            print("Wrote debug_output/nrma_raw.txt")
        except Exception:
            print("NRMA debug scrape failed:")
            traceback.print_exc()

        browser.close()


def run_full():
    os.makedirs(config.HISTORY_DIR, exist_ok=True)
    mapping = load_mapping()
    all_records = []
    errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS)
        page = browser.new_page()

        dates = list(daterange(config.START_DATE, config.END_DATE))
        total = len(dates) * 2

        for idx, d in enumerate(dates):
            for site_name, scraper in (("discovery_jindabyne", discovery),
                                        ("nrma_jindabyne", nrma)):
                step = idx * 2 + (0 if scraper is discovery else 1) + 1
                print(f"[{step}/{total}] {site_name} {d.isoformat()}")
                try:
                    records = scraper.scrape(
                        page, d, config.ADULTS, config.CHILDREN, config.INFANTS
                    )
                    all_records.extend(records)
                except Exception as e:
                    print(f"  ! failed: {e}")
                    errors.append({"site": site_name, "date": d.isoformat(), "error": str(e)})
                time.sleep(config.DELAY_BETWEEN_REQUESTS_SECONDS)

        browser.close()

    timestamp = date.today().isoformat()
    snapshot_path = os.path.join(config.HISTORY_DIR, f"{timestamp}.json")
    output = {
        "generated_at": timestamp,
        "ktp_rates": config.KTP_RATES,
        "mapping": mapping,
        "records": all_records,
        "errors": errors,
    }

    with open(snapshot_path, "w") as f:
        json.dump(output, f, indent=2)
    with open(config.LATEST_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nDone. {len(all_records)} records, {len(errors)} errors.")
    print(f"Saved to {snapshot_path} and {config.LATEST_FILE}")
    if errors:
        print("Some dates failed to scrape - see 'errors' in the output file.")


if __name__ == "__main__":
    if "--debug" in sys.argv:
        run_debug()
    else:
        run_full()
