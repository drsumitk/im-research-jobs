"""Oracle Recruiting Cloud candidate-experience sites (hcmRestApi recruitingCEJobRequisitions)."""
from urllib.parse import quote

from ..models import Job
from ..textutil import html_to_text, iso_date

PAGE = 25
MAX_PAGES = 4


def _list_url(src, term, offset):
    finder = (f"findReqs;siteNumber={src['site']},limit={PAGE},offset={offset},"
              f"keyword=%22{quote(term)}%22,sortBy=POSTING_DATES_DESC")
    return (f"https://{src['host']}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
            f"?onlyData=true&expand=requisitionList&finder={finder}")


def _job_url(src, job_id):
    return f"https://{src['host']}/hcmUI/CandidateExperience/en/sites/{src['site']}/job/{job_id}"


def parse_list(data, src):
    items = data.get("items") or [{}]
    it = items[0]
    jobs = []
    for r in it.get("requisitionList") or []:
        jobs.append(Job(
            source_id=src["id"],
            job_id=str(r.get("Id")),
            title=(r.get("Title") or "").strip(),
            url=_job_url(src, r.get("Id")),
            location=r.get("PrimaryLocation") or "",
            department=r.get("Department") or r.get("Organization") or "",
            posted=iso_date(r.get("PostedDate")),
            extra={"short": r.get("ShortDescriptionStr") or ""},
        ))
    return jobs, int(it.get("TotalJobsCount") or 0)


def parse_detail(data, job):
    it = (data.get("items") or [{}])[0]
    parts = [it.get("ExternalDescriptionStr"), it.get("ExternalResponsibilitiesStr"),
             it.get("ExternalQualificationsStr"), it.get("OrganizationDescriptionStr")]
    job.description = "\n".join(html_to_text(p) for p in parts if p)
    if it.get("ExternalPostedStartDate"):
        job.posted = iso_date(it["ExternalPostedStartDate"])
    dept = it.get("Department") or it.get("Organization")
    if dept and not job.department:
        job.department = dept
    return job


def search(http, src, terms, title_ok):
    seen = {}
    for term in terms:
        for page in range(MAX_PAGES):
            r = http.get(_list_url(src, term, page * PAGE), headers={"Accept": "application/json"})
            jobs, total = parse_list(r.json(), src)
            for j in jobs:
                seen.setdefault(j.key, j)
            if (page + 1) * PAGE >= total or not jobs:
                break
    return list(seen.values())


def details(http, src, job):
    url = (f"https://{src['host']}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
           f"?expand=all&onlyData=true&finder=ById;Id=%22{job.job_id}%22,siteNumber={src['site']}")
    r = http.get(url, headers={"Accept": "application/json"})
    return parse_detail(r.json(), job)
