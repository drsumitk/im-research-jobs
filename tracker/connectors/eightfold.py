"""Eightfold career sites (e.g. hiring.jhu.edu), via the site's /api/pcsx endpoints."""
from urllib.parse import quote

from ..models import Job
from ..textutil import html_to_text, iso_date

PAGE = 10  # the site returns 10 positions per page
MAX_PAGES = 6


def parse_list(data, src):
    d = data.get("data") or {}
    jobs = []
    for p in d.get("positions") or []:
        jobs.append(Job(
            source_id=src["id"],
            job_id=str(p.get("atsJobId") or p.get("id")),
            title=(p.get("name") or "").strip(),
            url=f"https://{src['host']}{p.get('positionUrl') or ''}",
            location="; ".join(p.get("locations") or []),
            department=p.get("department") or "",
            posted=iso_date(p.get("postedTs") or p.get("creationTs")),
            extra={"pid": p.get("id")},
        ))
    return jobs, int(d.get("count") or 0)


def parse_detail(data, job):
    d = data.get("data") or {}
    job.description = html_to_text(d.get("jobDescription") or "")
    fam = d.get("efcustomTextJobSubfamily") or []
    if fam and not job.department:
        job.department = ", ".join(fam)
    if d.get("publicUrl"):
        job.url = d["publicUrl"]
    return job


def search(http, src, terms, title_ok):
    seen = {}
    for term in terms:
        for page in range(MAX_PAGES):
            url = (f"https://{src['host']}/api/pcsx/search?domain={src['domain']}"
                   f"&query={quote(term)}&location=&start={page * PAGE}&sort_by=timestamp")
            r = http.get(url, headers={"Accept": "application/json"})
            jobs, total = parse_list(r.json(), src)
            for j in jobs:
                seen.setdefault(j.key, j)
            if (page + 1) * PAGE >= total or not jobs:
                break
    return list(seen.values())


def details(http, src, job):
    url = (f"https://{src['host']}/api/pcsx/position_details?position_id={job.extra['pid']}"
           f"&domain={src['domain']}&hl=en")
    r = http.get(url, headers={"Accept": "application/json"})
    return parse_detail(r.json(), job)
