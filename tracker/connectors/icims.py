"""iCIMS "classic" career portals (careers-xxx.icims.com, postdoctoral-xxx.icims.com).

The search and job pages are read with in_iframe=1, which returns the plain listing HTML that the
portal normally shows inside a frame. The schema.org datePosted on iCIMS job pages is not the real
posting date (it is generated relative to the time of the request), so it is not used. Some portals
show the real "Posted Date" in the list; where they do not, the posting has no known date.
"""
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from ..models import Job
from ..textutil import find_date, html_to_text

MAX_PAGES = 5


def _text(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el is not None else ""


def parse_list(page_html, src):
    soup = BeautifulSoup(page_html, "html.parser")
    jobs, seen = [], set()
    for a in soup.select("a.iCIMS_Anchor[href]"):
        m = re.search(r"/jobs/(\d+)/[^/?#]+/job", a["href"])
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        h = a.find(["h3", "h2"])
        title = _text(h) or re.sub(r"^\d+\s*-\s*", "", a.get("title", "")).strip()
        row = a.find_parent("div", class_="row")
        dept = ""
        if row is not None:
            for dt in row.find_all("dt"):
                if "department" in _text(dt).lower():
                    dd = dt.find_next_sibling("dd")
                    dept = _text(dd)
                    break
        posted = ""
        if row is not None:  # some portals show "Posted Date" with the exact time in a title attribute
            lab = row.find("span", class_="field-label", string=re.compile("Posted Date", re.I))
            val = lab.find_next_sibling("span") if lab is not None else None
            if val is not None:
                posted = find_date(val.get("title", "") or _text(val))
        url = re.sub(r"\?.*$", "", a["href"])
        if url.startswith("/"):
            url = f"https://{src['host']}{url}"
        jobs.append(Job(source_id=src["id"], job_id=m.group(1), title=title, url=url, department=dept,
                        posted=posted))
    return jobs


def parse_detail(page_html, job):
    soup = BeautifulSoup(page_html, "html.parser")
    el = soup.select_one(".iCIMS_JobContent") or soup.body
    job.description = html_to_text(str(el)) if el is not None else ""
    if job.department and "Department:" not in job.description[:400]:
        job.description = f"Department: {job.department}\n{job.description}"
    return job


def search(http, src, terms, title_ok):
    seen = {}
    for term in terms:
        for page in range(int(src.get("max_pages", MAX_PAGES))):
            url = (f"https://{src['host']}/jobs/search?ss=1&in_iframe=1&pr={page}"
                   f"&searchKeyword={quote(term)}")
            html = http.get(url).text
            jobs = parse_list(html, src)
            for j in jobs:
                seen.setdefault(j.key, j)
            if not jobs or not re.search(rf"[?&]pr={page + 1}\b", html):
                break
    return list(seen.values())


def details(http, src, job):
    return parse_detail(http.get(job.url + "?in_iframe=1").text, job)
