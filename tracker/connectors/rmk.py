"""SAP SuccessFactors career sites (Recruiting Marketing pages: /search/?q=..., /job/.../ID/)."""
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from ..models import Job
from ..textutil import html_to_text, iso_date

MAX_PAGES = 4


def parse_list(html, src):
    soup = BeautifulSoup(html, "html.parser")
    jobs, seen = [], set()
    rows = soup.select("tr.data-row") or soup.select("li.job-tile")
    for row in rows:
        a = row.select_one("a.jobTitle-link")
        if not a or not a.get("href"):
            continue
        href = a["href"]
        m = re.search(r"/(\d+)/?$", href)
        jid = m.group(1) if m else href
        if jid in seen:
            continue
        seen.add(jid)
        date_el = row.select_one("td.colDate .jobDate") or row.select_one(".jobDate")
        fac = row.select_one(".jobFacility")
        loc = row.select_one(".jobLocation")
        jobs.append(Job(
            source_id=src["id"], job_id=jid, title=a.get_text(strip=True),
            url=f"https://{src['host']}{href}",
            location=loc.get_text(" ", strip=True) if loc else "",
            department=fac.get_text(" ", strip=True) if fac else "",
            posted=iso_date(date_el.get_text(strip=True)) if date_el else "",
        ))
    total = 0
    lab = soup.select_one(".paginationLabel")
    if lab:
        nums = re.findall(r"\d+", lab.get_text(" "))
        if nums:
            total = int(nums[-1])
    else:
        m = re.search(r"of (\d+) Jobs", html)
        total = int(m.group(1)) if m else len(jobs)
    return jobs, total


def parse_detail(html, job):
    soup = BeautifulSoup(html, "html.parser")
    desc = soup.select_one('[itemprop="description"]')
    job.description = html_to_text(str(desc)) if desc else ""
    dp = soup.select_one('[itemprop="datePosted"]')
    if dp and dp.get("content"):
        job.posted = iso_date(dp["content"])
    return job


def search(http, src, terms, title_ok):
    seen = {}
    for term in terms:
        start = 0
        for _ in range(MAX_PAGES):
            url = (f"https://{src['host']}/search/?q={quote(term)}"
                   f"&sortColumn=referencedate&sortDirection=desc&startrow={start}")
            jobs, total = parse_list(http.get(url).text, src)
            for j in jobs:
                seen.setdefault(j.key, j)
            start += len(jobs)
            if not jobs or start >= total:
                break
    return list(seen.values())


def details(http, src, job):
    return parse_detail(http.get(job.url).text, job)
