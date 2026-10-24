"""Phenom People career sites (e.g. jobs.bswhealth.com).

The search page's own data endpoint (POST /widgets, refineSearch) returns jobs with titles and
posting dates, newest first. Each job page embeds its full description in the page data (phApp.ddo).
"""
import json
import re

from ..models import Job
from ..textutil import html_to_text, iso_date

PAGE = 50
MAX_PAGES = 2


def _body(term, start, src):
    return {
        "lang": src.get("lang", "en_us"), "deviceType": "desktop", "country": src.get("country", "us"),
        "pageName": "search-results", "ddoKey": "refineSearch", "sortBy": "Most recent", "subsearch": "",
        "from": start, "jobs": True, "counts": False, "all_fields": [], "size": PAGE, "clearAll": False,
        "jdsource": "facets", "isSliderEnable": False, "siteType": "external", "keywords": term,
        "global": True, "selected_fields": {}, "locationData": {},
    }


def parse_list(data, src):
    d = (data or {}).get("refineSearch") or {}
    jobs = []
    for x in (d.get("data") or {}).get("jobs") or []:
        jid = str(x.get("jobId") or x.get("reqId") or "")
        if not jid:
            continue
        jobs.append(Job(
            source_id=src["id"], job_id=jid, title=(x.get("title") or "").strip(),
            url=f"https://{src['host']}{src.get('path', '/us/en')}/job/{jid}",
            location=", ".join(v for v in (x.get("city"), x.get("state")) if v),
            department=x.get("category") or "",
            posted=iso_date(x.get("postedDate")),
        ))
    return jobs, int(d.get("totalHits") or 0)


def parse_detail(page_html, job):
    m = re.search(r"phApp\.ddo\s*=\s*(\{.*?\});\s*phApp\.", page_html, re.S)
    if m:
        try:
            j = ((json.loads(m.group(1)).get("jobDetail") or {}).get("data") or {}).get("job") or {}
        except ValueError:
            j = {}
        job.description = html_to_text(j.get("description") or "")
        job.posted = iso_date(j.get("postedDate")) or job.posted
    return job


def search(http, src, terms, title_ok):
    seen = {}
    for term in terms:
        for page in range(MAX_PAGES):
            r = http.post(f"https://{src['host']}/widgets", data=json.dumps(_body(term, page * PAGE, src)),
                          headers={"Content-Type": "application/json", "Accept": "application/json"})
            jobs, total = parse_list(r.json(), src)
            for j in jobs:
                seen.setdefault(j.key, j)
            if len(jobs) < PAGE or (page + 1) * PAGE >= total:
                break
    return list(seen.values())


def details(http, src, job):
    return parse_detail(http.get(job.url).text, job)
