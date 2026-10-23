"""Oracle Taleo career sections (REST search used by the career section page; job detail page)."""
import html as htmlmod
import json
import re
from urllib.parse import unquote

from bs4 import BeautifulSoup

from ..models import Job
from ..textutil import html_to_text

MAX_PAGES = 4


def _body(term, page):
    return {
        "multilineEnabled": True,
        "sortingSelection": {"sortBySelectionParam": "5", "ascendingSortingOrder": "false"},
        "fieldData": {"fields": {"KEYWORD": term, "LOCATION": "", "ORGANIZATION": ""}, "valid": True},
        "filterSelectionParam": {"searchFilterSelections": [
            {"id": "POSTING_DATE", "selectedValues": []},
            {"id": "LOCATION", "selectedValues": []},
            {"id": "JOB_FIELD", "selectedValues": []}]},
        "advancedSearchFiltersSelectionParam": {"searchFilterSelections": []},
        "pageNo": page,
    }


def parse_list(data, src):
    jobs = []
    for r in data.get("requisitionList") or []:
        cols = r.get("column") or []
        loc = ""
        for i in r.get("locationsColumns") or []:
            if i < len(cols):
                try:
                    loc = ", ".join(json.loads(cols[i]))
                except (ValueError, TypeError):
                    loc = cols[i]
        contest = r.get("contestNo") or r.get("jobId")
        jobs.append(Job(
            source_id=src["id"],
            job_id=str(contest),
            title=(cols[0] if cols else "").strip(),
            url=f"https://{src['host']}/careersection/{src['section']}/jobdetail.ftl?job={contest}&lang=en",
            location=loc,
        ))
    paging = data.get("pagingData") or {}
    return jobs, int(paging.get("totalCount") or 0), int(paging.get("pageSize") or 25)


def parse_detail(page_html, job):
    soup = BeautifulSoup(page_html, "html.parser")
    inp = soup.find("input", id="initialHistory")
    raw = inp.get("value", "") if inp else ""
    desc_html = ""
    for seg in raw.split("!|!"):
        if "!*!" in seg:
            desc_html = seg.split("!*!", 1)[1]
            break
    desc_html = unquote(desc_html).replace("\\:", ":")
    job.description = html_to_text(htmlmod.unescape(desc_html))
    m = re.search(r"Department\s*:?\s*\|?\s*([^\n]{3,120})", job.description)
    if m and not job.department:
        job.department = m.group(1).strip()
    return job


def search(http, src, terms, title_ok):
    seen = {}
    must = [s.lower() for s in src.get("location_must_include", [])]
    url = f"https://{src['host']}/careersection/rest/jobboard/searchjobs?lang=en&portal={src['portal']}"
    headers = {"Content-Type": "application/json", "tz": "GMT-06:00", "tzname": "America/Denver"}
    for term in terms:
        for page in range(1, MAX_PAGES + 1):
            r = http.post(url, data=json.dumps(_body(term, page)), headers=headers)
            jobs, total, size = parse_list(r.json(), src)
            for j in jobs:
                if must and not any(m in j.location.lower() for m in must):
                    continue
                seen.setdefault(j.key, j)
            if page * size >= total or not jobs:
                break
    return list(seen.values())


def details(http, src, job):
    return parse_detail(http.get(job.url).text, job)
