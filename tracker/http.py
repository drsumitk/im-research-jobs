"""Polite HTTP client: one session, timeouts, retries, per-host pacing, robots.txt (incl. crawl-delay)."""
import time
from urllib.parse import urlparse

import requests

from .robots import Robots

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 IMResearchJobTracker/1.0 (personal job search)"
)
TIMEOUT = 30
MIN_GAP_SECONDS = 1.0     # pause between requests to the same host
MAX_GAP_SECONDS = 10.0    # cap on a site's crawl-delay
RETRY_STATUSES = {429, 500, 502, 503, 504}


class FetchError(Exception):
    pass


class RobotsBlocked(FetchError):
    pass


class Http:
    def __init__(self, respect_robots=True, max_requests_per_host=300):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
        self.respect_robots = respect_robots
        self.max_requests_per_host = max_requests_per_host
        self._last, self._count, self._robots, self._robots_note = {}, {}, {}, {}

    def _robots_for(self, scheme, host):
        if host not in self._robots:
            # RFC 9309: 4xx (no robots.txt) means allowed; 5xx or no answer means treat as disallowed.
            text = "User-agent: *\nDisallow: /"
            self._robots_note[host] = "robots.txt could not be read (no answer), so the site is skipped today"
            try:
                r = self.session.get(f"{scheme}://{host}/robots.txt", timeout=TIMEOUT)
                if r.status_code == 200:
                    text = "" if "text/html" in r.headers.get("content-type", "") else r.text
                    self._robots_note[host] = ""
                elif 400 <= r.status_code < 500:
                    text = ""
                    self._robots_note[host] = ""
                else:
                    self._robots_note[host] = (f"robots.txt could not be read (HTTP {r.status_code}, site may be "
                                               "down for maintenance), so the site is skipped today")
            except requests.RequestException:
                pass
            self._robots[host] = Robots(text)
        return self._robots[host]

    def _pace(self, host, delay):
        n = self._count.get(host, 0)
        if n >= self.max_requests_per_host:
            raise FetchError(f"request cap reached for {host}")
        self._count[host] = n + 1
        last = self._last.get(host)
        if last is not None:
            wait = delay - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last[host] = time.monotonic()

    def request(self, method, url, **kw):
        p = urlparse(url)
        delay = MIN_GAP_SECONDS
        if self.respect_robots:
            rb = self._robots_for(p.scheme, p.netloc)
            path = p.path + (f"?{p.query}" if p.query else "")
            if not rb.allowed(path or "/"):
                raise RobotsBlocked(self._robots_note.get(p.netloc) or f"robots.txt disallows {p.netloc}{p.path}")
            if rb.crawl_delay:
                delay = min(max(rb.crawl_delay, MIN_GAP_SECONDS), MAX_GAP_SECONDS)
        kw.setdefault("timeout", TIMEOUT)
        last_exc = None
        for attempt in range(3):
            self._pace(p.netloc, delay)
            try:
                r = self.session.request(method, url, **kw)
            except requests.RequestException as e:
                last_exc = e
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code in RETRY_STATUSES:
                last_exc = FetchError(f"HTTP {r.status_code} from {p.netloc}")
                time.sleep(3 * (attempt + 1))
                continue
            if r.status_code >= 400:
                raise FetchError(f"HTTP {r.status_code} from {p.netloc}{p.path}")
            return r
        raise FetchError(str(last_exc))

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)
