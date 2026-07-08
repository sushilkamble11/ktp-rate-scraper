"""
Configuration for the KTP competitor rate scraper.
Edit the values below to suit — nothing here needs code changes elsewhere.
"""

from datetime import date, timedelta

# --- Date range to scan ---------------------------------------------------
DAYS_AHEAD = 90              # rolling window, starting tomorrow
START_DATE = date.today() + timedelta(days=1)
END_DATE = START_DATE + timedelta(days=DAYS_AHEAD)

# --- Politeness / stability ------------------------------------------------
DELAY_BETWEEN_REQUESTS_SECONDS = 2.5   # pause between each page load
PAGE_TIMEOUT_MS = 30000                 # how long to wait for a page to load
HEADLESS = True                         # set False to watch the browser work

# --- Search params ----------------------------------------------------------
ADULTS = 2
CHILDREN = 0
INFANTS = 0

# --- Your own KTP rates, for the dashboard comparison -----------------------
# Fill these in / keep updated. Used only for display in dashboard.html.
# Values are indicative nightly rates in AUD — adjust to match your current
# published rate for each category (e.g. your peak-season Fri/Sat rate).
KTP_RATES = {
    "unpowered": None,       # e.g. 55
    "powered": None,         # e.g. 65
    "2br_chalet": None,      # e.g. 320
    "2br_upgraded": None,    # e.g. 380
    "3br_chalet": None,      # e.g. 450
    "cedar": None,           # e.g. 250
}

# --- Output locations --------------------------------------------------------
# Lives under docs/ so GitHub Pages can serve the dashboard + data directly.
HISTORY_DIR = "docs/history"
LATEST_FILE = "docs/history/latest.json"
