# KTP Rate Desk

Every Monday morning this reads the nightly rates of **Kosciuszko Tourist Park**,
**Discovery Parks Jindabyne** and **NRMA Jindabyne Holiday Park** out to
**December 2028**, lines each KTP category up against the closest like-for-like
competitor room, and tells you where to move your rates.

- **Rates compared:** KTP's public direct rate vs each competitor's **member** rate
  (Discovery Club 10% off, capped at $50 a booking; My NRMA 10% off the flexible rate, capped at $60 a booking).
  Nightly, 2 adults. Min-stay nights are priced as a share of the minimum stay.
- **Market** = average of the competitor rooms marked `exact` or `close` in `mapping.json`.
- **Flags:** *Raise* when you're the cheapest and 10%+ under the market (or 5%+ under
  while a competitor is sold out). *Lower* when you're the dearest and 15%+ over.
  Suggested rate = market rate rounded to $5. Grouped by month and weeknights vs
  Fri & Sat nights, biggest dollar gap first.
- **Opening-rate guide:** for months where your rates aren't loaded yet but a
  competitor's are, the market rate per month to start from.
- **Extras:** extra adult / child charge per night for every park.
- **Week on week:** competitor rate moves of $10+ and 10%+.

It reads the same booking data each park's own website uses (a nightly rate
calendar), so ~150 requests cover 27 months and layout changes don't break it.
Parks only load rates so far ahead – later months fill in as they open them.

## What you get each week

| Where | What |
|---|---|
| Rate Desk page (claude.ai) | The dashboard: what to change, opening-rate guide, month-by-month heatmap, extras, moves |
| Email | Top raise / lower suggestions and competitor moves, dashboard + CSV attached |
| `reports/latest.html` | Same dashboard as a file – open in a browser |
| `reports/latest.csv` | Every night × category, for Excel |
| Actions → run → Summary | Coverage and top suggestions |
| `data/snapshots/` | Raw nightly rates for every run (gzip JSON), used for week-on-week moves |

If a park that's meant to be covered fails or returns nothing, the run goes
**red** and the email subject says **DATA MISSING**.

## One-time setup

1. **Make the repo private** – Settings → General → Change visibility → Private.
2. **Email secrets** – Settings → Secrets and variables → Actions:
   `SMTP_HOST`, `SMTP_PORT` (465 or 587), `SMTP_USERNAME`, `SMTP_PASSWORD`,
   `REPORT_TO` (comma separated), optional `REPORT_FROM`.

## NRMA needs a local computer

NRMA's firewall blocks cloud servers, including GitHub's. On GitHub the run
covers KTP vs Discovery and leaves NRMA out. To include NRMA, connect a computer
that's usually on (the park office PC is ideal) as a **self-hosted runner**
(Settings → Actions → Runners → New self-hosted runner; on Linux/Mac finish with
`./svc.sh install && ./svc.sh start`), then add the Actions variable
`RUNNER` = `self-hosted`. `PARKS` (optional variable) overrides the park list.

## Adding your GuestPoint rates

KTP is currently read from the live SiteMinder booking engine
(`KTP_CHANNEL` in `config.py`). When rates open on GuestPoint, add a
`scrapers/guestpoint.py` returning the same nightly records and switch
`PARKS["ktp"]` in `run.py` to it.

## Changing things

- **Mapping:** `mapping.json` – competitor room per KTP category, `match` =
  `exact`, `close` or `none` (reference only, never flagged).
- **Thresholds, horizon, delays:** `config.py`.
- **Schedule:** `cron` in `.github/workflows/scrape.yml` (UTC).

## Running it yourself

```bash
pip install -r requirements.txt
python -m playwright install chromium
python run.py --end 2027-03-31 --no-email   # shorter window
python run.py --only nrma                   # one park
python run.py --rebuild                     # re-render from data/latest.json.gz
python -m pytest -q tests                   # offline tests
```

## Where the numbers come from

| Park | Source |
|---|---|
| KTP | SiteMinder booking engine (`book-directonline.com`, channel `kosciuszkotouristpark-1`): 90-day nightly calendars; single-date queries for min-stay nights and extra guests |
| Discovery | G'day Group API (`exp-api.gdaygroup.com.au`, park `NJIN`): one call returns every room's 12-month nightly calendar; extras from the itemised rate breakdown |
| NRMA | NRMA site API (`/api/accommodation/get-availability-pricing/`): monthly ranges, Standard Rate per night (member = 10% off, max $60); nights after the last bookable night are "rates loaded, not bookable yet"; $9,999 block-outs are ignored |
