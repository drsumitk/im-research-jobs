"""Postdoc-office job boards and other simple HTML lists (one row per opening).

Configured entirely in sources.yaml with CSS selectors, for example:

  type: board
  url: https://postdocs.yale.edu/applicants/open-positions?page={page}
                           # {q} in the url is replaced by each search term (search-result pages)
  pages: 4                 # read pages page_start .. page_start+pages-1 (only when url has {page})
  page_start: 0
  row: li.reference-card   # one opening
  link: a                  # link to the opening's own page (optional)
  title: a                 # where the title is (optional; default: link text)
  title_template: "Postdoctoral position: {dept}"  # optional; may use {title} {dept} {mentor}
  dept: td:nth-of-type(2)  # optional CSS for the department
  dept_caption: true       # optional: department from the row's table <caption>
  mentor: td:nth-of-type(4)
  location: p.muted        # optional CSS for the location / hospital
  date: td:nth-of-type(1)  # optional CSS for the posting date; default: a <time> or the first date in the row
  detail: main             # CSS for the description on the opening's page, or "none" to use the row text
  detail_date_label: "Advertising Started on:"   # optional: posting date printed after this label
  detail_ldjson_date: true # optional: posting date from the page's schema.org JobPosting
  sitemap_dates: https://site/sitemap.xml   # optional: undated openings take the sitemap's last-modified
                           # date, an upper bound on the posting date (a posting may be older, never newer)

Boards list only postdoc openings, so a title_template that starts with "Postdoctoral" keeps the
title rules from dropping openings whose own titles are just a mentor's name.
"""
import hashlib
import re
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from ..models import Job
from ..textutil import find_date, html_to_text, iso_date


def _text(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el is not None else ""


def _page_urls(src, terms=()):
    """List pages to read: one per search term when the url has {q}, one per page when it has {page}."""
    urls = [src["url"].replace("{q}", quote_plus(t)) for t in terms] if "{q}" in src["url"] else [src["url"]]
    if "{page}" not in src["url"]:
        return urls
    start = int(src.get("page_start", 0))
    return [u.replace("{page}", str(p)) for u in urls for p in range(start, start + int(src.get("pages", 1)))]


def parse_list(page_html, src, page_url):
    soup = BeautifulSoup(page_html, "html.parser")
    jobs = []
    for row in soup.select(src["row"]):
        link = row.select_one(src["link"]) if src.get("link") else None
        href = link.get("href") if link is not None else None
        if src.get("link") and not href:
            continue  # header rows and spacer rows have no link
        title_el = row.select_one(src["title"]) if src.get("title") else link
        fields = {
            "title": _text(title_el),
            "dept": _text(row.select_one(src["dept"])) if src.get("dept") else "",
            "mentor": _text(row.select_one(src["mentor"])) if src.get("mentor") else "",
        }
        if src.get("dept_caption") and not fields["dept"]:
            cap = row.find_parent("table")
            cap = cap.find("caption") if cap is not None else None
            fields["dept"] = re.sub(r"^\s*Department\s*:\s*", "", _text(cap))
        if src.get("date") == "none":
            posted = ""  # the row has numbers that are not dates; the detail page gives the date
        elif src.get("date"):
            posted = find_date(_text(row.select_one(src["date"])))
        else:
            t = row.find("time")
            posted = iso_date(t["datetime"]) if t is not None and t.get("datetime") else find_date(_text(row))
        title = src["title_template"].format(**fields) if src.get("title_template") else fields["title"]
        title = re.sub(r"\(\s*\)", "", re.sub(r"\s+", " ", title)).strip(" -:,")  # drop empty "()" from templates
        if not title:
            continue
        url = urljoin(page_url, href) if href else page_url
        row_text = _text(row)
        jid = re.sub(r"[^A-Za-z0-9]+", "-", re.sub(r"^https?://[^/]+", "", url)).strip("-") if href \
            else hashlib.sha256(row_text.encode("utf-8")).hexdigest()[:12]
        loc = _text(row.select_one(src["location"])) if src.get("location") else ""
        job = Job(source_id=src["id"], job_id=jid, title=title, url=url,
                  department=fields["dept"], posted=posted, location=loc)
        if src.get("detail") == "none":
            job.description = html_to_text(str(row))
            if job.department:
                job.description = f"Department: {job.department}\n{job.description}"
        jobs.append(job)
    return jobs


def parse_detail(page_html, job, src):
    soup = BeautifulSoup(page_html, "html.parser")
    el = soup.select_one(src.get("detail") or "main") or soup.find("main") or soup.body
    job.description = html_to_text(str(el)) if el is not None else ""
    if src.get("detail_ldjson_date"):  # schema.org JobPosting datePosted on the opening's page
        for sc in soup.find_all("script", type="application/ld+json"):
            m = re.search(r'"datePosted"\s*:\s*"([^"]+)"', sc.string or "")
            if m:
                job.posted = iso_date(m.group(1)) or job.posted
                break
    label = src.get("detail_date_label")
    if label:
        text = re.sub(r"\s+", " ", soup.get_text(" "))
        i = text.find(label)
        if i >= 0:
            job.posted = find_date(text[i + len(label): i + len(label) + 80]) or job.posted
    if job.department and "Department:" not in job.description[:400]:
        job.description = f"Department: {job.department}\n{job.description}"
    return job


def search(http, src, terms, title_ok):
    seen = {}
    for url in _page_urls(src, terms):
        page_jobs = parse_list(http.get(url).text, src, url)
        for j in page_jobs:
            seen.setdefault(j.key, j)
        if not page_jobs and "{q}" not in src["url"]:
            break  # paged list ran out
    if src.get("sitemap_dates") and seen:
        lastmod = sitemap_lastmod(http.get(src["sitemap_dates"]).text)
        for j in seen.values():
            if not j.posted:
                j.posted = lastmod.get(j.url.rstrip("/"), "")
    return list(seen.values())


def sitemap_lastmod(xml_text):
    """{url without trailing slash: YYYY-MM-DD} from a sitemap's <url> entries."""
    out = {}
    for block in re.findall(r"<url>(.*?)</url>", xml_text, re.S):
        loc = re.search(r"<loc>\s*(.*?)\s*</loc>", block, re.S)
        mod = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", block, re.S)
        if loc and mod:
            out[loc.group(1).strip().rstrip("/")] = iso_date(mod.group(1).strip())
    return out


def details(http, src, job):
    if src.get("detail") == "none":
        return job
    return parse_detail(http.get(job.url).text, job, src)
