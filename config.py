"""
Settings for the KTP competitor rate check. Everything tunable lives here.
Category mapping lives in mapping.json.
"""

# --- What to price ------------------------------------------------------------
DAYS_AHEAD = 120          # rolling window of check-in dates, starting tomorrow
ADULTS = 2                # base occupancy every park prices at
# Every night is priced as a 1-night stay (2 adults), plus every Friday as a
# Fri->Sun 2-night stay, so weekends with a 2-night minimum still get a price.

# --- How close counts as "in line" --------------------------------------------
IN_LINE_BAND_PCT = 5      # KTP within +/-5% of the competitor = in line

# --- Week-on-week alerts -------------------------------------------------------
MOVE_MIN_DOLLARS = 10     # flag competitor price moves of at least $10 ...
MOVE_MIN_PCT = 10         # ... and at least 10%

# --- Politeness / reliability --------------------------------------------------
DELAY_SECONDS = 1.0       # pause between requests to the same site
TIMEOUT_SECONDS = 30
RETRIES = 3

# --- Sites ---------------------------------------------------------------------
KTP_CHANNEL = "kosciuszkotouristpark-1"            # SiteMinder booking engine
KTP_BASE = "https://book-directonline.com"
KTP_RANGE_MAX_DAYS = 90                            # engine caps a range at ~92 days

DISCOVERY_PARK_CODE = "NJIN"
DISCOVERY_API = "https://exp-api.gdaygroup.com.au/api/v1"
DISCOVERY_PAGE = "https://www.discoveryholidayparks.com.au/caravan-parks/new-south-wales/snowy-mountains/jindabyne"
DISCOVERY_CALLER = "DhpWeb"                        # header their own site sends

NRMA_BASE = "https://www.nrmaparksandresorts.com.au"
NRMA_PAGE = "https://www.nrmaparksandresorts.com.au/jindabyne/book-now/"
NRMA_PARK_NAME = "NRMA Jindabyne Holiday Park"
NRMA_API_KEY = "instances_efa54796e4116207d567ad259e53a819"  # public key their site sends

# --- Output ----------------------------------------------------------------------
DATA_DIR = "data"
SNAPSHOT_DIR = "data/snapshots"
REPORT_DIR = "reports"
