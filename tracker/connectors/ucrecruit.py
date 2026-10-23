"""University of California "Recruit" academic job sites, read from their public Atom feed (/apply.atom).
The feed lists every open academic recruitment (mostly faculty); the title filter keeps the research ones."""
import re
import xml.etree.ElementTree as ET

from ..models import Job
from ..textutil import html_to_text, iso_date

NS = {"a": "http://www.w3.org/2005/Atom"}


def parse_feed(xml_text, src):
    root = ET.fromstring(xml_text)
    jobs = []
    for e in root.findall("a:entry", NS):
        link = e.find("a:link", NS)
        url = link.get("href") if link is not None else (e.findtext("a:id", default="", namespaces=NS))
        jid = url.rstrip("/").rsplit("/", 1)[-1]
        summary = e.find("a:summary", NS)
        content = e.find("a:content", NS)
        body = ""
        for node in (content, summary):
            if node is not None:
                body = ET.tostring(node, encoding="unicode", method="xml")
                break
        text = html_to_text(re.sub(r"</?(ns\d+:|a:)?(summary|content)[^>]*>", "", body))
        jobs.append(Job(
            source_id=src["id"], job_id=jid,
            title=(e.findtext("a:title", default="", namespaces=NS) or "").strip(),
            url=url,
            posted=iso_date(e.findtext("a:published", default="", namespaces=NS)),
            description=text,
        ))
    return jobs


def search(http, src, terms, title_ok):
    r = http.get(f"https://{src['host']}/apply.atom")
    return parse_feed(r.text, src)


def details(http, src, job):
    return job
