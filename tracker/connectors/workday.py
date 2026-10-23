"""Workday career sites (*.myworkdayjobs.com, *.myworkdaysite.com).
Uses the JSON endpoint that the career site's own search box calls (not an officially documented API)."""
import re
from datetime import date, timedelta

from ..models import Job
from ..textutil import html_to_text, iso_date

PAGE = 20
MAX_PAGES = 5


def _base(src):
    return f"https://{src['host']}/wday/cxs/{src['tenant']}/{src['site']}"


def posted_from_text(text, today=None):
    """'Posted Today' -> date; 'Posted 3 Days Ago' -> date; '30+ Days Ago' -> '30+ days ago'."""
    today = today or date.today()
    t = (text or "").lower()
    if "today" in t:
        return today.isoformat()
    if "yesterday" in t:
        return (today - timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\+? days? ago", t)
    if m:
        if "+" in t:
            return f"{m.group(1)}+ days ago"
        return (today - timedelta(days=int(m.group(1)))).isoformat()
    return text or ""


def parse_list(data, src, today=None):
    jobs = []
    for p in data.get("jobPostings", []) or []:
        path = p.get("externalPath") or ""
        if not path:
            continue
        bullets = p.get("bulletFields") or []
        req = bullets[0] if bullets else path.rsplit("_", 1)[-1]
        jobs.append(Job(
            department=" / ".join(bullets[1:]),
            source_id=src["id"],
            job_id=str(req),
            title=(p.get("title") or "").strip(),
            url=f"https://{src['host']}/{src['site']}{path}" if "myworkdayjobs" in src["host"]
                else f"https://{src['host']}/recruiting/{src['tenant']}/{src['site']}{path}",
            location=p.get("locationsText") or "",
            posted=posted_from_text(p.get("postedOn"), today),
            extra={"path": path},
        ))
    return jobs, int(data.get("total") or 0)


def parse_detail(data, job):
    info = data.get("jobPostingInfo") or {}
    job.description = html_to_text(info.get("jobDescription", ""))
    if info.get("startDate"):
        job.posted = iso_date(info["startDate"])
    if info.get("externalUrl"):
        job.url = info["externalUrl"]
    if info.get("location") and not job.location:
        job.location = info["location"]
    return job


def search(http, src, terms, title_ok):
    seen = {}
    for term in terms:
        total = None
        for page in range(MAX_PAGES):
            body = {"appliedFacets": {}, "limit": PAGE, "offset": page * PAGE, "searchText": term}
            r = http.post(_base(src) + "/jobs", json=body, headers={"Accept": "application/json"})
            jobs, page_total = parse_list(r.json(), src)
            if total is None:
                total = page_total  # Workday may report the total only on the first page
            for j in jobs:
                seen.setdefault(j.key, j)
            if len(jobs) < PAGE or (total and (page + 1) * PAGE >= total):
                break
    return list(seen.values())


def details(http, src, job):
    r = http.get(_base(src) + job.extra["path"], headers={"Accept": "application/json"})
    return parse_detail(r.json(), job)
