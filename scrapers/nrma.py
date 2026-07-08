"""
Scraper for NRMA Jindabyne Holiday Park.

Unlike Discovery, NRMA's booking widget doesn't take dates via URL params -
you have to open the calendar and click the arrival/departure day cells.
The calendar shows two months at a time and only moves forward via a
"next month" arrow, so we calculate how many times to click that arrow
based on how far out the target date is from today.

Their rate API (api/accommodation/get-availability-pricing) requires a
client-side header key baked into their JS bundle. We deliberately do NOT
extract or replay that key directly - that would mean reverse-engineering
an access control mechanism rather than just reading public prices. So we
drive the actual page/UI instead, the same way a visitor would, and read
the rendered result.
"""

import re
from datetime import date

URL = "https://www.nrmaparksandresorts.com.au/jindabyne/book-now/"

SLEEPS_RE = re.compile(r"^Sleeps:\s*(\d+)$")
BEDROOMS_RE = re.compile(r"^Bedrooms:\s*(\d+)$")
PRICE_RE = re.compile(r"^\$(\d+)$")
TOTAL_RE = re.compile(r"^Total \$(\d+)$")
NIGHTLY_FROM_RE = re.compile(r"^Nightly rate from \$(\d+)$")

SKIP_LINES = {
    "See all features and inclusions",
    "Join My NRMA Rewards and save up to 10%",
    "Change dates",
    "See all rates",
    "Book",
    "Edit",
    "Non-refundable",
    "Special rate",
    "Non-members",
    "Avg./night",
    "My NRMA Rewards members",
    "PET FRIENDLY",
    "NEW",
    "Minimum 2 night stay",
}


def _month_diff(from_date: date, to_date: date) -> int:
    return (to_date.year - from_date.year) * 12 + (to_date.month - from_date.month)


def _select_date_range(page, arrive: date, depart: date):
    """Opens the date picker and selects arrive/depart, then applies."""
    page.get_by_role("button", name=re.compile(r".*\d{4}|Enter dates")).first.click()
    page.wait_for_selector("text=Select dates", timeout=10000)

    today = date.today()
    # Calendar opens showing [this month, next month]. Click "next month"
    # (the '>' arrow) enough times to bring the target month into view.
    clicks_needed = max(0, _month_diff(today, arrive))
    # The forward arrow's accessible name may differ slightly from this if
    # NRMA changes their markup - check debug_output if this stops working.
    for _ in range(clicks_needed):
        page.locator("[aria-label='Next month'], button:has-text('›'), button:has-text('>')").first.click()
        page.wait_for_timeout(150)

    # Day-of-month suffix (st/nd/rd/th) varies, so match loosely instead.
    arrive_cell = page.get_by_role(
        "gridcell", name=re.compile(rf"{arrive.day}(st|nd|rd|th), {arrive.year}")
    ).first
    arrive_cell.click()

    depart_cell = page.get_by_role(
        "gridcell", name=re.compile(rf"{depart.day}(st|nd|rd|th), {depart.year}")
    ).first
    depart_cell.click()

    page.get_by_role("button", name="Apply").click()
    page.wait_for_timeout(1500)


def parse_page_text(text: str, scrape_date: date):
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Only look at the accommodation listing section.
    try:
        start = next(i for i, l in enumerate(lines) if "accommodation options" in l)
    except StopIteration:
        start = 0

    records = []
    i = start + 1
    n = len(lines)

    while i < n:
        line = lines[i]

        if line in SKIP_LINES or line.startswith("BOOK NOW") or line.startswith("LAST ONE"):
            i += 1
            continue
        if line == "Discover":  # footer reached, stop
            break

        # Candidate: room name line
        name = line
        i += 1

        sleeps = None
        bedrooms = None
        # Next few lines may be Sleeps / Bedrooms / Car / "Open plan" / tags
        while i < n and (
            SLEEPS_RE.match(lines[i]) or BEDROOMS_RE.match(lines[i])
            or lines[i].startswith("Car:") or lines[i] == "Open plan"
            or lines[i] in SKIP_LINES
        ):
            m_sleeps = SLEEPS_RE.match(lines[i])
            m_bed = BEDROOMS_RE.match(lines[i])
            if m_sleeps:
                sleeps = int(m_sleeps.group(1))
            if m_bed:
                bedrooms = int(m_bed.group(1))
            i += 1

        # Skip the description line if present (heuristic: not a known
        # marker and doesn't look like a price/date line).
        if i < n and not lines[i].startswith("$") and "rate" not in lines[i].lower() \
                and lines[i] != "See all features and inclusions" \
                and not lines[i][0].isdigit():
            i += 1  # description text

        if i < n and lines[i] == "See all features and inclusions":
            i += 1

        # Pricing block: order and exact lines differ between site-style
        # cards (locked single-night rate) and cabin-style cards ("from"
        # rate across a wider window), so scan forward with a bounded
        # lookahead rather than assuming a fixed line order.
        price = None
        price_member = None
        is_site_style = False
        limit = min(n, i + 20)
        j = i

        while j < limit:
            line_j = lines[j]

            if NIGHTLY_FROM_RE.match(line_j):
                price = int(NIGHTLY_FROM_RE.match(line_j).group(1))
                j += 1
                break

            if re.match(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d", line_j):
                # Both card styles show a date-range line - it doesn't by
                # itself tell us which style this is, so just skip over it.
                j += 1
                continue

            if line_j == "Non-members":
                j += 1
                if j < limit and lines[j] == "Avg./night":
                    j += 1
                if j < limit and PRICE_RE.match(lines[j]):
                    price = int(PRICE_RE.match(lines[j]).group(1))
                    is_site_style = True
                    j += 1
                if j < limit and TOTAL_RE.match(lines[j]):
                    j += 1
                continue

            if line_j == "My NRMA Rewards members":
                j += 1
                if j < limit and lines[j] == "Avg./night":
                    j += 1
                if j < limit and PRICE_RE.match(lines[j]):
                    price_member = int(PRICE_RE.match(lines[j]).group(1))
                    j += 1
                if j < limit and TOTAL_RE.match(lines[j]):
                    j += 1
                continue

            if line_j in ("See all rates", "Book", "Change dates"):
                j += 1
                break

            # Anything else in this window (Non-refundable, Special rate,
            # Edit, Join My NRMA Rewards..., Minimum N night stay, etc.)
            # is preamble/trailer noise - skip over it.
            j += 1

        i = j

        if price is None:
            continue  # parsing didn't line up - skip this record safely

        records.append({
            "competitor": "nrma_jindabyne",
            "category": None,
            "name": name,
            "sleeps": sleeps,
            "bedrooms": bedrooms,
            "price": price,
            "price_member": price_member,
            "available": True,
            "rate_is_approximate": is_site_style is False,
            "scrape_date": scrape_date.isoformat(),
        })

    return records


def scrape(page, target_date: date, adults: int, kids: int, infants: int):
    depart = date.fromordinal(target_date.toordinal() + 1)

    page.goto(URL, wait_until="networkidle", timeout=30000)
    _select_date_range(page, target_date, depart)

    try:
        page.wait_for_selector("text=accommodation options", timeout=15000)
    except Exception:
        return []

    text = page.inner_text("main")
    return parse_page_text(text, target_date)
