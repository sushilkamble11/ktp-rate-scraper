"""
Settings for the KTP competitor rate check. Everything tunable lives here.
Category mapping lives in mapping.json.
"""
from datetime import date

# --- What to collect -------------------------------------------------------------
END_DATE = date(2028, 12, 31)   # collect nightly rates from tomorrow up to here
ADULTS = 2                      # base occupancy every park prices at
# Every park is read as a nightly rate calendar (2 adults). Parks only publish
# rates a certain distance ahead; later months fill in as they open them.

PLACEHOLDER_RATE = 5000         # nightly "rates" this high are block-out placeholders
                                # (NRMA uses $9,999) - treated as not open

# --- What counts as a gap worth acting on ---------------------------------------
IN_LINE_BAND_PCT = 5            # within +/-5% of market = in line
RAISE_GAP_PCT = 10              # KTP 10%+ below market -> "raise"
LOWER_GAP_PCT = 15              # KTP 15%+ above market -> "consider lowering"
ROUND_TO = 5                    # suggested rates rounded to the nearest $5

# --- Week-on-week alerts -------------------------------------------------------
MOVE_MIN_DOLLARS = 10           # flag competitor price moves of at least $10 ...
MOVE_MIN_PCT = 10               # ... and at least 10%

# --- Politeness / reliability --------------------------------------------------
DELAY_SECONDS = 1.0             # pause between requests to the same site
TIMEOUT_SECONDS = 45
RETRIES = 3

# --- Sites ---------------------------------------------------------------------
KTP_CHANNEL = "kosciuszkotouristpark-1"            # SiteMinder booking engine
KTP_BASE = "https://book-directonline.com"
KTP_RANGE_DAYS = 90                                # calendar chunk size

DISCOVERY_PARK_CODE = "NJIN"
DISCOVERY_API = "https://exp-api.gdaygroup.com.au/api/v1"
DISCOVERY_PAGE = "https://www.discoveryholidayparks.com.au/caravan-parks/new-south-wales/snowy-mountains/jindabyne"
DISCOVERY_CALLER = "DhpWeb"                        # header their own site sends
DISCOVERY_MEMBER_PCT = 10                          # Discovery Club: 10% off ...
DISCOVERY_MEMBER_CAP = 50                          # ... capped at $50 a booking

NRMA_BASE = "https://www.nrmaparksandresorts.com.au"
NRMA_PAGE = "https://www.nrmaparksandresorts.com.au/jindabyne/book-now/"
NRMA_PARK_NAME = "NRMA Jindabyne Holiday Park"
NRMA_API_KEY = "instances_efa54796e4116207d567ad259e53a819"  # public key their site sends
NRMA_MEMBER_PCT = 10                               # My NRMA: 10% off ...
NRMA_MEMBER_CAP = 60                               # ... capped at $60 a booking
NRMA_RANGE_DAYS = 31                               # calendar chunk size (max ~91)

# --- Output ----------------------------------------------------------------------
DATA_DIR = "data"
SNAPSHOT_DIR = "data/snapshots"
REPORT_DIR = "reports"
