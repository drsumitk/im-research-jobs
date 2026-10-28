"""Job lists that a site builds with JavaScript: the page is opened in headless Chromium
(tracker.browser) and the rendered HTML is read with the same CSS settings as a "board" source:

  type: rendered
  url: https://uic.csod.com/ux/ats/careersite/1/home?c=uic&sq={q}
  wait_for: 'a[href*="/requisition/"]'   # CSS that appears once the list has loaded
  row / link / title / dept / location / date: as for type board
  detail: none | CSS selector on the rendered job page
  detail_date_label: 'Posted Date'       # optional

Job pages are rendered only for titles that pass the title rules and that the tracker has not read
before, at most MAX_DETAILS per run; any left over are read on the next run.
"""
from . import board
from ..browser import Browser

MAX_DETAILS = 40


def search(http, src, terms, title_ok):
    known = src.get("_known") or set()
    seen = {}
    with Browser(http) as br:
        for url in board._page_urls(src, terms):
            html, final = br.render(url, wait_for=src.get("wait_for"))
            page_jobs = board.parse_list(html, src, final)
            for j in page_jobs:
                seen.setdefault(j.key, j)
            if not page_jobs and "{q}" not in src["url"]:
                break  # paged list ran out
        if src.get("detail", "none") != "none":
            done = 0
            for j in seen.values():
                if done >= MAX_DETAILS:
                    break
                if j.key in known or not title_ok(j.title):
                    continue
                html, _ = br.render(j.url, wait_for=src.get("detail"))
                board.parse_detail(html, j, src)
                done += 1
    return list(seen.values())


def details(http, src, job):
    return job  # job pages are rendered inside search(), while the browser is open
