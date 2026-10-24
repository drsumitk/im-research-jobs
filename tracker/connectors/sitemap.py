"""Career sites that publish every open job in an XML sitemap (for example careers.harvard.edu).

The sitemap is the list meant for crawlers, so it is used instead of the search page. A rough title
is read from each job URL; only titles that pass the title rules are opened. Detail pages carry a
schema.org JobPosting block with the real title, description and posting date.
"""
import html as htmlmod
import json
import re
from urllib.parse import unquote

from bs4 import BeautifulSoup

from ..models import Job
from ..textutil import html_to_text, iso_date


def title_from_slug(slug):
    """'research-assistant-iii-non-lab-in-boston-ma-united-states-jid-2240' -> 'research assistant iii non lab'."""
    m = re.match(r"^(.*)-in-.*?jid-\d+$", slug)
    base = m.group(1) if m else re.sub(r"-?jid-\d+$", "", slug)
    return unquote(base).replace("-", " ").strip()


def parse_sitemap(xml_text, src):
    pat = re.compile(src.get("link_pattern", r"/job/[^/]+-jid-(\d+)$"))
    jobs = []
    for block in re.findall(r"<url>(.*?)</url>", xml_text, re.S):
        loc = re.search(r"<loc>\s*(.*?)\s*</loc>", block, re.S)
        if not loc:
            continue
        url = htmlmod.unescape(loc.group(1))
        m = pat.search(url)
        if not m:
            continue
        lastmod = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", block, re.S)
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        jobs.append(Job(
            source_id=src["id"],
            job_id=m.group(1),
            title=title_from_slug(slug),
            url=url,
            # A job cannot have been posted after the sitemap's last-modified date, so this is a safe
            # upper bound for the age filter. The detail page replaces it with the real posting date.
            posted=iso_date(lastmod.group(1)) if lastmod else "",
        ))
    return jobs


def _field(soup, name):
    li = soup.select_one(f"li.{name}-wrapper")
    if not li:
        return ""
    label = li.find("label")
    if label:
        label.extract()
    return li.get_text(" ", strip=True)


def parse_detail(page_html, job):
    soup = BeautifulSoup(page_html, "html.parser")
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
        except ValueError:
            continue
        for o in data if isinstance(data, list) else [data]:
            if isinstance(o, dict) and o.get("@type") == "JobPosting":
                job.title = (o.get("title") or job.title).strip()
                job.description = html_to_text(o.get("description", ""))
                job.posted = iso_date(o.get("datePosted")) or job.posted
                loc = o.get("jobLocation")
                if isinstance(loc, list) and loc:
                    loc = loc[0]
                addr = loc.get("address", {}) if isinstance(loc, dict) else {}
                if isinstance(addr, dict) and addr.get("addressLocality"):
                    job.location = addr["addressLocality"]
                break
    unit, dept = _field(soup, "Brand"), _field(soup, "Department")
    job.department = " / ".join(v for v in (unit, dept) if v) or job.department
    if dept:
        job.description = f"Department: {dept}\n{job.description}"
    return job


def search(http, src, terms, title_ok):
    return parse_sitemap(http.get(src["sitemap_url"]).text, src)


def details(http, src, job):
    return parse_detail(http.get(job.url).text, job)
