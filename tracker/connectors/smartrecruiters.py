"""SmartRecruiters public Posting API (used by Harvard University):
https://api.smartrecruiters.com/v1/companies/{company}/postings"""
from urllib.parse import quote

from ..models import Job
from ..textutil import html_to_text, iso_date

API = "https://api.smartrecruiters.com/v1/companies"
LIMIT = 100
MAX_PAGES = 3


def parse_list(data, src):
    jobs = []
    for p in data.get("content") or []:
        loc = p.get("location") or {}
        dept = p.get("department") or {}
        jobs.append(Job(
            source_id=src["id"],
            job_id=str(p.get("id")),
            title=(p.get("name") or "").strip(),
            url=f"https://jobs.smartrecruiters.com/{src['company']}/{p.get('id')}",
            location=loc.get("fullLocation") or ", ".join(v for v in [loc.get("city"), loc.get("region")] if v),
            department=dept.get("label") or "",
            posted=iso_date(p.get("releasedDate")),
            extra={"ref": p.get("ref")},
        ))
    return jobs, int(data.get("totalFound") or 0)


def parse_detail(data, job):
    sections = ((data.get("jobAd") or {}).get("sections") or {})
    parts = [sections.get(k, {}).get("text", "") for k in ("jobDescription", "qualifications", "additionalInformation")]
    job.description = "\n".join(html_to_text(p) for p in parts if p)
    if data.get("postingUrl"):
        job.url = data["postingUrl"]
    if data.get("releasedDate"):
        job.posted = iso_date(data["releasedDate"])
    return job


def search(http, src, terms, title_ok):
    seen = {}
    for term in terms:
        for page in range(MAX_PAGES):
            url = f"{API}/{src['company']}/postings?q={quote(term)}&limit={LIMIT}&offset={page * LIMIT}"
            jobs, total = parse_list(http.get(url, headers={"Accept": "application/json"}).json(), src)
            for j in jobs:
                seen.setdefault(j.key, j)
            if (page + 1) * LIMIT >= total or not jobs:
                break
    return list(seen.values())


def details(http, src, job):
    ref = job.extra.get("ref") or f"{API}/{src['company']}/postings/{job.job_id}"
    return parse_detail(http.get(ref, headers={"Accept": "application/json"}).json(), job)
