# KTP Competitor Rate Scraper

Scrapes public nightly rates from two Jindabyne competitors — NRMA Jindabyne
Holiday Park and Discovery Parks Jindabyne — for the next 90 days, maps
their room/site categories to KTP's 8 categories, and shows a dashboard of
where you're priced above/below the market.

This runs entirely on **GitHub Actions** — GitHub's free automation runners.
Once set up, it runs itself every night: no server, no VPS, nothing on your
own computer needs to stay on.

## One-time setup (about 15 minutes)

### 1. Create a GitHub account (skip if you have one)
Go to https://github.com/signup — free.

### 2. Create a new repository
- Click the **+** (top right) → **New repository**
- Name it e.g. `ktp-rate-scraper`
- Set it to **Private** (keeps your KTP rates in `config.py` out of public view)
- Don't add a README/gitignore in the setup screen (this project already has them)
- Click **Create repository**

### 3. Upload this project
On the new repo's page, click **uploading an existing file**, then drag in
every file and folder from this project (keeping the folder structure —
`.github/`, `docs/`, `scrapers/`, etc.) and commit.

(If you're comfortable with git instead: `git init`, `git add .`,
`git commit -m "Initial commit"`, then follow GitHub's "push an existing
repository" instructions on the repo's empty-state page.)

### 4. Turn on GitHub Pages (this hosts your dashboard)
- In the repo, go to **Settings → Pages**
- Under "Build and deployment" → Source: **Deploy from a branch**
- Branch: **main**, folder: **/docs** → **Save**
- After a minute or two, GitHub shows you a URL like:
  `https://yourusername.github.io/ktp-rate-scraper/dashboard.html`
  — bookmark that. That's your dashboard, live on the internet (only
  people with the link can find it, but it's not password protected —
  see the note on privacy below).

### 5. Run it for the first time
- Go to the **Actions** tab → click **"Scrape competitor rates"** on the
  left → click **Run workflow** (button on the right) → **Run workflow**
  again to confirm.
- This kicks off the same job that'll run automatically every night.
  Click into the running job to watch its progress — a full run takes
  roughly 20-40 minutes (90 dates × 2 sites, with a polite delay between
  requests so we're not hammering their servers).
- When it finishes, refresh your dashboard URL from step 4 — it should
  show real data.

That's it — from here it runs automatically every night on its own.

## Editing your own KTP rates

Open `config.py` in the repo (GitHub's web editor is fine — click the
pencil icon on the file) and fill in `KTP_RATES` with your current
published rate per category. Commit the change. It'll show up on the
dashboard next time the scraper runs (or trigger it manually via Actions
→ Run workflow if you want it sooner).

## Editing the category mapping

`mapping.json` maps your 8 categories to each competitor's named
room/site types. Two gaps are flagged and need your input:

- **3BR Chalet**: neither competitor has a genuine 3-bedroom cabin. The
  mapping currently points at each site's largest 2BR unit as a soft
  proxy — treat that comparison with a grain of salt.
- **Cedar Cabin**: left empty. Tell me Cedar's bed count/sleeps capacity
  and I'll fill in the right competitor tier (or edit `mapping.json`
  yourself — it's plain JSON, editable straight in GitHub's web editor).

## Changing the schedule

`.github/workflows/scrape.yml` has the cron line:
```
- cron: '0 17 * * *'
```
That's 17:00 UTC, roughly 3-4am at Jindabyne depending on daylight saving
(GitHub Actions cron is always in UTC). Change the two numbers
(`minute hour`) to shift the time — e.g. `0 15 * * *` runs an hour or two
earlier locally.

## A privacy note on GitHub Pages

The dashboard URL from step 4 isn't listed anywhere or searchable, but
it's also not password-protected — anyone with the exact link could view
it. It only shows competitor rates and (if you fill it in) your own rates
per category, not anything more sensitive. If that's a concern, keep the
repo private (as in step 2) and instead just download `docs/history/
latest.json` from the repo each morning and open `docs/dashboard.html`
locally — a little more manual, but nothing leaves your control.

## If a scrape breaks

Both competitor sites are React/Next.js apps that could change their
markup at any time, which would break the text parsing in
`scrapers/discovery.py` / `scrapers/nrma.py`. If the Actions run shows a
red ✗, click into it to see the error, or trigger a run with a debug
flag locally (`python run_scraper.py --debug`, needs Playwright installed
on your own machine) to dump the raw page text to `debug_output/` — send
that over and I'll help fix the parser.

## A note on scope

This was built and validated against real captured page text from both
sites in one session — both parsers were tested and produce correct
output against that sample. But I can't run the actual live scrape
myself (my environment can't reach these websites), so treat the very
first automated run as a shakedown: check a date or two against what you
see manually before fully trusting the numbers, and send me any errors
so we can patch them together.
