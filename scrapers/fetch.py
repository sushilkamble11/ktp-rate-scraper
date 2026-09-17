"""
JSON fetching with two modes per site:

1. plain HTTP (fast, what we try first)
2. from inside a real Chromium tab on the site's own page, using the page's
   fetch(). Used automatically if a site blocks plain HTTP (403/429, bot
   challenge, HTML instead of JSON). This is the same request the site's own
   booking page makes, so it gets through whatever the browser gets through.

Once a site falls back to browser mode it stays there for the rest of the run.
"""

import json
import logging
import os
import time

import httpx

import config

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

BLOCK_STATUSES = {401, 403, 405, 407, 429}


class FetchError(Exception):
    pass


class Blocked(FetchError):
    pass


class Fetcher:
    def __init__(self, delay=config.DELAY_SECONDS, force_browser=False):
        self.delay = delay
        self.force_browser = force_browser
        self.client = httpx.Client(
            timeout=config.TIMEOUT_SECONDS,
            headers={"User-Agent": UA, "Accept-Language": "en-AU,en;q=0.9"},
            follow_redirects=True,
        )
        self.browser_sites = set()
        self._pw = None
        self._browser = None
        self._pages = {}
        self._last = {}
        self.calls = 0

    # -- public ---------------------------------------------------------------
    def get_json(self, site: str, warmup_url: str, url: str, headers: dict | None = None):
        """GET url and return parsed JSON. `site` groups politeness + fallback."""
        headers = {"Accept": "application/json", **(headers or {})}
        last_err = None
        for attempt in range(1, config.RETRIES + 1):
            self._wait(site)
            try:
                if self.force_browser or site in self.browser_sites:
                    return self._browser_get(site, warmup_url, url, headers)
                try:
                    return self._http_get(url, headers)
                except Blocked as e:
                    log.warning("%s blocked plain HTTP (%s) - switching to browser mode", site, e)
                    self.browser_sites.add(site)
                    return self._browser_get(site, warmup_url, url, headers)
            except FetchError as e:
                last_err = e
                log.warning("%s attempt %d failed: %s", site, attempt, e)
                time.sleep(2 * attempt)
        raise FetchError(f"{site}: gave up after {config.RETRIES} attempts: {last_err}")

    def close(self):
        self.client.close()
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    # -- internals ------------------------------------------------------------
    def _wait(self, site):
        gap = time.monotonic() - self._last.get(site, 0)
        if gap < self.delay:
            time.sleep(self.delay - gap)
        self._last[site] = time.monotonic()
        self.calls += 1

    def _http_get(self, url, headers):
        try:
            r = self.client.get(url, headers=headers)
        except httpx.HTTPError as e:
            raise FetchError(f"network: {e}") from e
        return self._parse(r.status_code, r.text, r.headers.get("content-type", ""))

    @staticmethod
    def _parse(status, text, ctype=""):
        if status in BLOCK_STATUSES:
            raise Blocked(f"HTTP {status}")
        stripped = text.lstrip()[:200].lower()
        if stripped.startswith("<") or "captcha" in stripped or "challenge" in stripped:
            raise Blocked(f"HTTP {status} returned HTML, not JSON")
        if status >= 400:
            raise FetchError(f"HTTP {status}: {text[:200]}")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise FetchError(f"bad JSON (HTTP {status}): {text[:200]}") from e

    def _launch(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        # Look like an ordinary visitor: real Chrome if installed, a real
        # (virtual) display when one exists, no automation flag.
        kw = dict(headless=not os.environ.get("DISPLAY"),
                  args=["--disable-blink-features=AutomationControlled"])
        try:
            self._browser = self._pw.chromium.launch(channel="chrome", **kw)
        except Exception:
            self._browser = self._pw.chromium.launch(**kw)
        log.info("browser: %s %s, headless=%s", self._browser.browser_type.name,
                 self._browser.version, kw["headless"])

    def _page_for(self, site, warmup_url):
        if site in self._pages:
            return self._pages[site]
        if not self._pw:
            self._launch()
        ctx = self._browser.new_context(locale="en-AU", timezone_id="Australia/Sydney",
                                        viewport={"width": 1366, "height": 900})
        ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = ctx.new_page()
        page.goto(warmup_url, wait_until="domcontentloaded",
                  timeout=config.TIMEOUT_SECONDS * 2000)
        # Wait out any "checking your browser" interstitial.
        title = ""
        for _ in range(40):
            title = (page.title() or "").lower()
            if not any(k in title for k in ("just a moment", "attention required",
                                            "access denied", "checking")):
                break
            page.wait_for_timeout(1000)
        page.wait_for_timeout(3000)
        log.info("%s warm-up page title: %r", site, page.title())
        self._pages[site] = page
        return page

    def _browser_get(self, site, warmup_url, url, headers):
        try:
            page = self._page_for(site, warmup_url)
            res = page.evaluate(
                """async ({url, headers}) => {
                     const r = await fetch(url, {headers, credentials: 'include'});
                     return {status: r.status, text: await r.text(),
                             ctype: r.headers.get('content-type') || ''};
                   }""",
                {"url": url, "headers": headers},
            )
        except Exception as e:  # playwright errors
            self._pages.pop(site, None)
            raise FetchError(f"browser: {e}") from e
        try:
            return self._parse(res["status"], res["text"], res["ctype"])
        except Blocked as e:
            self._pages.pop(site, None)   # reload the page next attempt
            raise FetchError(f"blocked even in browser: {e}") from e
