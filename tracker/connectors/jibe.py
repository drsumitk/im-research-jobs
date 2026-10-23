"""iCIMS Jibe career sites (/api/jobs JSON, used by e.g. jobs.ucla.edu and careers.mountsinai.org).
The list response already contains the full description, so no detail call is needed."""
from urllib.parse import quote

from ..models import Job
from ..textutil import html_to_text, iso_date

LIMIT = 100
MAX_PAGES = 2


def parse_list(data, src):
    jobs = []
    for item in data.get("jobs") or []:
        d = item.get("data") or {}
        url = ((d.get("meta_data") or {}).get("canonical_url")
               or f"https://{src['host']}/jobs/{d.get('slug')}")
        cats = d.get("category") or []
        jobs.append(Job(
            source_id=src["id"],
            job_id=str(d.get("req_id") or d.get("slug")),
            title=(d.get("title") or "").strip(),
            url=url,
            location=", ".join(x for x in [d.get("city"), d.get("state")] if x),
            department=", ".join(c.strip() for c in cats if c) if isinstance(cats, list) else str(cats),
            posted=iso_date(d.get("posted_date")),
            description=html_to_text(d.get("description") or ""),
        ))
    return jobs, int(data.get("totalCount") or 0)


def search(http, src, terms, title_ok):
    seen = {}
    for term in terms:
        for page in range(1, MAX_PAGES + 1):
            url = (f"https://{src['host']}/api/jobs?keywords={quote(term)}"
                   f"&sortBy=posted_date&descending=true&page={page}&limit={LIMIT}")
            jobs, total = parse_list(http.get(url, headers={"Accept": "application/json"}).json(), src)
            for j in jobs:
                seen.setdefault(j.key, j)
            if page * LIMIT >= total or not jobs:
                break
    return list(seen.values())


def details(http, src, job):
    return job  # description already present
