"""
Scraper for Discovery Parks - Jindabyne.

Discovery's park page accepts arrive/depart/adults/kids/infants as URL
query params, but the room list + prices are loaded client-side (React)
after the page loads, so we still need a real browser to render it.
"""

import re
from datetime import date

BASE_URL = "https://www.discoveryholidayparks.com.au/caravan-parks/new-south-wales/snowy-mountains/jindabyne"

# Lines that are page chrome, not room data - skip these when parsing.
SKIP_LINES = {
    "Sort by",
    "Highest Price First",
    "Cabins Only",
    "Sites Only",
    "Available for your dates",
    "Unavailable for your dates",
    "View Availability",
    "for members",
    "View Stay",
}

AVAILABILITY_TAG_RE = re.compile(r"^\d+ (Cabin|Site)s? Left$")
SLEEPS_RE = re.compile(r"^Sleeps (\d+)$")
PRICE_RE = re.compile(r"^\$(\d+)$")
AVAILABLE_FROM_RE = re.compile(r"^Available from")
GUESTS_LINE_RE = re.compile(r"^\d+ Adults?,")


def build_url(arrive: date, depart: date, adults: int, kids: int, infants: int) -> str:
    return (
        f"{BASE_URL}?arrive={arrive.isoformat()}&depart={depart.isoformat()}"
        f"&adults={adults}&kids={kids}&infants={infants}"
    )


def parse_page_text(text: str, scrape_date: date):
    """
    Parses the visible text of the room list into structured records.
    Returns a list of dicts: category, name, sleeps, price, price_member,
    available (bool), scrape_date.
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Find where the actual listing starts (after the date/guest header).
    start_idx = 0
    for i, line in enumerate(lines):
        if line == "Available for your dates":
            start_idx = i
            break

    records = []
    is_available_section = True
    i = start_idx
    n = len(lines)

    while i < n:
        line = lines[i]

        if line == "Available for your dates":
            is_available_section = True
            i += 1
            continue
        if line == "Unavailable for your dates":
            is_available_section = False
            i += 1
            continue
        if line in SKIP_LINES or GUESTS_LINE_RE.match(line):
            i += 1
            continue
        if AVAILABILITY_TAG_RE.match(line):
            # e.g. "1 Cabin Left" - informational, skip
            i += 1
            continue

        # Otherwise this should be a category line (e.g. "Deluxe Cabin",
        # "Powered Site"), followed by the room name.
        category = line
        i += 1
        if i >= n:
            break
        name = lines[i]
        i += 1

        sleeps = None
        if i < n:
            m = SLEEPS_RE.match(lines[i])
            if m:
                sleeps = int(m.group(1))
                i += 1

        if i < n and lines[i] == "View Availability":
            i += 1

        price = None
        price_member = None
        if i < n and PRICE_RE.match(lines[i]):
            price = int(PRICE_RE.match(lines[i]).group(1))
            i += 1
        if i < n and PRICE_RE.match(lines[i]):
            price_member = int(PRICE_RE.match(lines[i]).group(1))
            i += 1
        if i < n and lines[i] == "for members":
            i += 1

        if i < n and AVAILABLE_FROM_RE.match(lines[i]):
            i += 1  # e.g. "Available from 8 - 9 Jul" - note and skip

        if i < n and lines[i] == "View Stay":
            i += 1

        if price is None:
            # Didn't match expected shape - bail out of this record so we
            # don't cascade errors through the rest of the page.
            continue

        records.append({
            "competitor": "discovery_jindabyne",
            "category": category,
            "name": name,
            "sleeps": sleeps,
            "price": price,
            "price_member": price_member,
            "available": is_available_section,
            "scrape_date": scrape_date.isoformat(),
        })

    return records


def scrape(page, target_date: date, adults: int, kids: int, infants: int):
    """
    `page` is a Playwright page object. Navigates, waits for content,
    and returns parsed records for the given single-night stay.
    """
    depart = date.fromordinal(target_date.toordinal() + 1)
    url = build_url(target_date, depart, adults, kids, infants)

    page.goto(url, wait_until="networkidle", timeout=30000)

    # Wait for at least one room card to render.
    try:
        page.wait_for_selector("text=View Stay", timeout=15000)
    except Exception:
        # No rooms rendered (e.g. sold out or page structure changed) -
        # return empty rather than crashing the whole run.
        return []

    text = page.inner_text("main")
    return parse_page_text(text, target_date)
