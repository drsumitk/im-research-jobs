"""m-cloud job API used by jobs.nyulangone.org. The list response contains full descriptions."""
from urllib.parse import quote

from ..models import Job
from ..textutil import html_to_text, iso_date

API = "https://jobsapi-internal.m-cloud.io/api/job"
LIMIT = 50
MAX_PAGES = 3


def parse_list(data, src):
    jobs = []
    for x in data.get("queryResult") or []:
        url = (x.get("url") or "").replace("http://", "https://", 1)
        jobs.append(Job(
            source_id=src["id"],
            job_id=str(x.get("id")),
            title=(x.get("title") or "").strip(),
            url=url,
            location=", ".join(v for v in [x.get("primary_city"), x.get("primary_state")] if v),
            department=" / ".join(v for v in [x.get("department"), x.get("primary_category")] if v),
            posted=iso_date(x.get("open_date")),
            description=html_to_text(x.get("description") or ""),
        ))
    return jobs, int(data.get("totalHits") or 0)


def search(http, src, terms, title_ok):
    seen = {}
    for term in terms:
        for page in range(MAX_PAGES):
            url = (f"{API}?SearchText={quote(term)}&Limit={LIMIT}&Organization={src['organization']}"
                   f"&offset={page * LIMIT + 1}&sortfield=open_date&sortorder=descending")
            jobs, total = parse_list(http.get(url, headers={"Accept": "application/json"}).json(), src)
            for j in jobs:
                seen.setdefault(j.key, j)
            if (page + 1) * LIMIT >= total or not jobs:
                break
    return list(seen.values())


def details(http, src, job):
    return job
