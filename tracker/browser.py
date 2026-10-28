"""Headless Chromium for job sites that build their job list with JavaScript after the page opens.

The browser opens a page the way a person's browser would and returns the rendered HTML. It does not
hide that it is automated (Chromium's own headless user agent is kept), it checks robots.txt before
every page through tracker.http.Http, and it stops at a bot check instead of trying to pass it.
Images, fonts and media are not downloaded.
"""
import re

from .http import FetchError

BOT_CHECK = re.compile(
    r"verify (that )?you are (a )?human|are you a robot|are you human|captcha|unusual traffic|"
    r"checking your browser|access denied|request unsuccessful|incapsula|cf-chl|px-captcha|"
    r"enable javascript and cookies to continue", re.I)
SKIP_TYPES = {"image", "font", "media"}
NAV_TIMEOUT_MS = 45000


class BotCheck(FetchError):
    pass


class Browser:
    """Use as a context manager; one instance per thread (Playwright's sync API is per thread)."""

    def __init__(self, http):
        self.http = http
        self._pw = self._browser = self._ctx = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright  # installed only where rendered sources run
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._ctx = self._browser.new_context(locale="en-US")
        self._ctx.route("**/*", lambda route: route.abort() if route.request.resource_type in SKIP_TYPES
                        else route.continue_())
        return self

    def __exit__(self, *exc):
        for obj, meth in ((self._ctx, "close"), (self._browser, "close"), (self._pw, "stop")):
            try:
                if obj is not None:
                    getattr(obj, meth)()
            except Exception:
                pass

    def render(self, url, wait_for=None, settle_ms=2500):
        """Return (html, final_url). wait_for: CSS selector that appears once the job list has loaded."""
        self.http.check(url)
        page = self._ctx.new_page()
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            if resp is not None and resp.status >= 400:
                raise FetchError(f"HTTP {resp.status} from {url}")
            if wait_for:
                try:
                    page.wait_for_selector(wait_for, timeout=20000)
                except Exception:
                    pass  # no rows (no results) is a normal outcome; the caller sees an empty list
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            page.wait_for_timeout(settle_ms)
            html = page.content()
            visible = page.inner_text("body")[:5000] if page.query_selector("body") else ""
            if BOT_CHECK.search(visible) and len(visible) < 3000:
                raise BotCheck(f"bot check page at {url}; not bypassed")
            return html, page.url
        finally:
            page.close()
