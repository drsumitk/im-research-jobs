"""Generic server-rendered job lists: a search page with job links, and detail pages read either
from schema.org JobPosting JSON-LD ("ldjson") or from a CSS selector ("css")."""
import json
import re
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from ..models import Job
from ..textutil import find_date, html_to_text, iso_date


def parse_list(page_html, src):
    soup = BeautifulSoup(page_html, "html.parser")
    pat = re.compile(src["link_pattern"])
    jobs, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        path = re.sub(r"^https?://[^/]+", "", href)
        if not pat.search(path):
            continue
        t_el = a.select_one(src["title_selector"]) if src.get("title_selector") else None
        title = (t_el or a).get_text(" ", strip=True)
        if not title or title.lower() in ("apply now", "apply", "view job", "learn more"):
            continue
        if path in seen:
            continue
        seen.add(path)
        posted, dept = "", ""
        row = a.find_parent("tr")
        if row is not None:
            t = row.find("time") if src.get("row_time", True) else None  # some lists show a closing date
            if t and t.get("datetime"):
                posted = iso_date(t["datetime"])
            d = row.select_one('[class*="department"]')
            if d:
                dept = d.get_text(" ", strip=True)
        jid = re.sub(r"[^A-Za-z0-9]+", "-", path).strip("-")
        job = Job(source_id=src["id"], job_id=jid, title=title,
                  url=urljoin(f"https://{src['host']}/", path), posted=posted, department=dept)
        if src.get("detail") == "none":
            # Job pages cannot be read (e.g. bot protection): keep the list facts only.
            job.description = "\n".join(v for v in (f"Department: {dept}" if dept else "", title) if v)
        jobs.append(job)
    return jobs


def parse_detail(page_html, job, src):
    soup = BeautifulSoup(page_html, "html.parser")
    if src.get("detail") == "ldjson":
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "")
            except ValueError:
                continue
            for o in data if isinstance(data, list) else [data]:
                if isinstance(o, dict) and o.get("@type") == "JobPosting":
                    raw = o.get("description", "")
                    job.description = html_to_text(raw)
                    # UC San Diego style: <div class="jobSideHeader">Department:</div><span class="attrib">X</span>
                    side = BeautifulSoup(raw, "html.parser")
                    for h in side.select(".jobSideHeader"):
                        if h.get_text(strip=True).rstrip(":").lower() == "department":
                            val = h.find_next_sibling(class_="attrib")
                            if val and not job.department:
                                job.department = val.get_text(" ", strip=True)
                    job.posted = iso_date(o.get("datePosted")) or job.posted
                    loc = o.get("jobLocation")
                    if isinstance(loc, list) and loc:
                        loc = loc[0]
                    addr = (loc or {}).get("address", {}) if isinstance(loc, dict) else {}
                    if addr and not job.location:
                        job.location = ", ".join(v for v in [addr.get("addressLocality"), addr.get("addressRegion")] if v)
                    m = re.search(r"Department:\s*([^\n]{3,120})", job.description)
                    if m and not job.department:
                        job.department = m.group(1).strip()
                    return job
    else:
        el = soup.select_one(src.get("detail_selector", "main")) or soup.find("main") or soup.body
        job.description = html_to_text(str(el)) if el else ""
        if len(job.description) < 200 and soup.body is not None:  # selector missed: use the whole page
            job.description = html_to_text(str(soup.body))
    label = src.get("detail_date_label")
    if label:
        text = re.sub(r"\s+", " ", soup.get_text(" "))
        i = text.find(label)
        if i >= 0:
            job.posted = find_date(text[i + len(label): i + len(label) + 80]) or job.posted
    return job


def search(http, src, terms, title_ok):
    seen = {}
    for term in terms:
        url = f"https://{src['host']}{src['search_path'].format(q=quote(term))}"
        for j in parse_list(http.get(url).text, src):
            seen.setdefault(j.key, j)
    return list(seen.values())


def details(http, src, job):
    if src.get("detail") == "none":
        return job
    r = http.get(job.url)
    parse_detail(r.text, job, src)
    if not job.description:  # reported in the source's health entry so the cause can be seen
        raise RuntimeError(f"empty job page (HTTP {r.status_code}, {r.headers.get('content-type')}, "
                           f"{len(r.content)} bytes, encoding {r.headers.get('content-encoding')})")
    return job
