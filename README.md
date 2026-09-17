# KTP competitor rate check

Every Monday morning this checks what **Discovery Parks Jindabyne** and
**NRMA Jindabyne Holiday Park** are charging for the next 120 days, lines each
KTP category up against their closest like-for-like room, and emails a summary.

- **Prices compared:** KTP's lowest public direct price vs each competitor's
  **member** price (Discovery Club 10% off capped at $50 a booking; My NRMA 10% off
  the flexible rate).
- **Stays priced:** every night as a 1-night stay (2 adults), plus every Friday as
  a Fri–Sun 2-night stay so weekends with a minimum stay still get a price.
- **Extra guests:** extra adult and extra child charges per night for every park (checked on one weeknight each week).
- **Week on week:** competitor price moves of $10+ and 10%+ since last run.

It reads the same booking data each park's own website uses (no clicking
through pages), which is why it doesn't break when a site changes its layout.
If a site ever blocks plain requests it automatically switches to a real
browser for that site.

## What you get each week

| Where | What |
|---|---|
| Email | Summary table, extra-guest charges, biggest competitor price moves. Dashboard + CSV attached |
| `reports/latest.html` | Full dashboard – summary, by month, extras, moves, day-by-day detail, mapping. Download and open in a browser |
| `reports/latest.csv` | Every date and category side by side, for Excel |
| Actions → run → Summary | The summary table, right in GitHub |
| Actions → run → Artifacts | The week's dashboard + CSV as a download (kept 90 days) |
| `data/snapshots/` | Raw prices for every run (gzip JSON) – used for week-on-week moves |

If a park fails or returns no prices, the run goes **red**, the email subject
says **DATA MISSING**, and nothing empty gets saved.

## One-time setup

1. **Make the repo private** – Settings → General → Danger Zone → Change
   visibility → Private. (It contains your pricing history.)
2. **Add the email secrets** – Settings → Secrets and variables → Actions →
   New repository secret:

   | Secret | Example |
   |---|---|
   | `SMTP_HOST` | `smtp.hostinger.com` / `smtp.office365.com` |
   | `SMTP_PORT` | `465` (SSL) or `587` (STARTTLS) |
   | `SMTP_USERNAME` | the mailbox that sends it |
   | `SMTP_PASSWORD` | that mailbox's password / app password |
   | `REPORT_TO` | `stay@kosipark.com.au, you@example.com` |
   | `REPORT_FROM` | optional, defaults to `SMTP_USERNAME` |

   Without these it still runs and saves the report; it just doesn't email.
3. **Run it once now** – Actions → *Weekly competitor rates* → Run workflow.
   Takes about 15–20 minutes.

## Changing things

- **Category mapping:** `mapping.json`. Each KTP category lists the competitor
  room it's compared with and a `match` of `exact`, `close` or `none`. `none`
  is shown for reference only and left out of the score. Room ids come from
  the parks' booking systems; the run log warns if a mapped room disappears.
- **Window, "in line" band, move thresholds, delays:** `config.py`.
- **Schedule:** the `cron` line in `.github/workflows/scrape.yml` (UTC).
- **Add a competitor:** add a scraper in `scrapers/` returning records via
  `scrapers.common.record`, register it in `run.py`, and add it to
  `mapping.json`.

## Running it yourself

```bash
pip install -r requirements.txt
python -m playwright install chromium
python run.py --days 7 --no-email        # quick test
python run.py --only nrma --days 3       # one park
python run.py --rebuild                  # re-render reports from data/latest.json
python -m pytest -q tests                # parser + end-to-end tests (offline)
```

## Where the numbers come from

| Park | Source | Notes |
|---|---|---|
| KTP | SiteMinder booking engine API (`book-directonline.com`, channel `kosciuszkotouristpark-1`) | Nightly calendar for 1-night prices; single-date queries for Fri–Sun prices (lowest public price, includes Stay & Save where it applies) and extra guests (same charge for adults and children) |
| Discovery | G'day Group booking API (`exp-api.gdaygroup.com.au`, park `NJIN`) | Member price from the `MemberOffer`; extras from the itemised rate breakdown |
| NRMA | NRMA site API (`/api/accommodation/get-availability-pricing/`) | Standard (flexible) rate `MemberTotal`; extras from pricing 3 adults and 2 adults + 1 child |

Where a stay can't be booked as asked (usually a minimum-night rule) the
price is estimated from the nightly rate and marked `*`.
