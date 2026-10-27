"""Setup helper, run by hand from the "Probe sources" workflow (never by the daily scan).

  python -m tracker.probe --brimr URL        read a BRIMR ranking spreadsheet into probe/brimr.txt
  python -m tracker.probe --sites FILE       fingerprint careers pages listed in FILE (one "label | url" a line)
  python -m tracker.probe --only id1,id2     run candidate sources once and report what they find

Candidate sources live in config/probe_sources.yaml (same layout as sources.yaml). Every request goes
through tracker.http.Http, so robots.txt is respected exactly as in the daily scan. Results are written
to probe/ for the workflow to publish on the "probe" branch.
"""
import argparse
import io
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import run
from .http import Http, RobotsBlocked
from .rules import Rules

OUT = run.ROOT / "probe"

ATS_PATTERNS = {
    "workday": r"https?://[\w.-]+\.myworkdayjobs\.com/[^\s\"'<>]*",
    "oracle": r"https?://[\w.-]+\.oraclecloud\.com/hcmUI/CandidateExperience/[^\s\"'<>]*",
    "taleo": r"https?://[\w.-]+\.taleo\.net/[^\s\"'<>]*",
    "icims": r"https?://[\w.-]+\.icims\.com/[^\s\"'<>]*",
    "peopleadmin": r"https?://[\w.-]+\.peopleadmin\.com[^\s\"'<>]*",
    "pageup": r"https?://[\w.-]*pageuppeople\.com[^\s\"'<>]*",
    "successfactors": r"https?://[\w.-]*(?:successfactors|sapsf)\.(?:com|eu)[^\s\"'<>]*",
    "silkroad": r"https?://[\w.-]*silkroad\.com[^\s\"'<>]*",
    "ultipro": r"https?://[\w.-]*(?:ultipro|ukg)\.com[^\s\"'<>]*",
    "phenom": r"phApp|phenompeople|cdn\.phenompeople\.com",
    "jibe": r"jibeapply|/api/jobs\b|jibecdn",
    "eightfold": r"eightfold\.ai[^\s\"'<>]*",
    "rmk": r"rmkcdn|jobs2web|/go/[\w-]+/\d+/",
    "mcloud": r"mcloud|nlx|careers\.\w+\.org/mcloud",
    "interfolio": r"https?://apply\.interfolio\.com/[^\s\"'<>]*",
    "selectminds": r"https?://[\w.-]*selectminds\.com[^\s\"'<>]*",
    "adp": r"https?://workforcenow\.adp\.com[^\s\"'<>]*",
    "smartrecruiters": r"https?://(?:jobs|careers)\.smartrecruiters\.com/[^\s\"'<>]*",
    "brassring": r"https?://[\w.-]*brassring\.com[^\s\"'<>]*",
    "kenexa": r"https?://[\w.-]*kenexa\.com[^\s\"'<>]*",
    "cornerstone": r"https?://[\w.-]*csod\.com[^\s\"'<>]*",
    "jobvite": r"https?://jobs\.jobvite\.com/[^\s\"'<>]*",
    "greenhouse": r"https?://boards\.greenhouse\.io/[^\s\"'<>]*",
    "lever": r"https?://jobs\.lever\.co/[^\s\"'<>]*",
    "paycom": r"https?://[\w.-]*paycom(?:online)?\.(?:com|net)[^\s\"'<>]*",
    "hirebridge": r"https?://[\w.-]*hirebridge\.com[^\s\"'<>]*",
    "taleo_portal": r"portal[\"']?\s*[=:]\s*[\"']?\d{6,}",
    "csod": r"https?://[\w.-]+\.csod\.com[^\s\"'<>]*",
    "neogov": r"https?://www\.governmentjobs\.com/careers/[^\s\"'<>]*",
    "infor": r"https?://[\w.-]*cloud\.infor\.com[^\s\"'<>]*",
    "peoplesoft": r"https?://[\w.-]+/psc/[^\s\"'<>]*|HRS_HRAM|HRS_CE",
}
JOB_LINK = re.compile(r"career|jobs?\b|employment|opportunit|join our|work (?:at|for|with)|postdoc", re.I)


def _fingerprint(html):
    hits = {}
    for name, pat in ATS_PATTERNS.items():
        found = sorted(set(m.group(0)[:200] for m in re.finditer(pat, html)))
        if found:
            hits[name] = found[:5]
    return hits


def _save_html(label, text):
    d = OUT / "html"
    d.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9]+", "-", label).strip("-")[:60] or "page"
    (d / f"{name}.html").write_text(text[:400000], encoding="utf-8")


def probe_site(http, label, url):
    res = {"label": label, "url": url}
    try:
        r = http.get(url, allow_redirects=True)
    except RobotsBlocked as e:
        return dict(res, status="robots", note=str(e)[:200])
    except Exception as e:
        return dict(res, status="error", note=f"{type(e).__name__}: {str(e)[:200]}")
    _save_html(label, r.text)
    soup = BeautifulSoup(r.text, "html.parser")
    res.update(status=r.status_code, length=len(r.text), final=r.url, title=(soup.title.get_text(" ", strip=True)[:150] if soup.title else ""),
               ats=_fingerprint(r.text))
    links = []
    for a in soup.find_all("a", href=True):
        t = " ".join(a.get_text(" ", strip=True).split())[:80]
        if JOB_LINK.search(t) or JOB_LINK.search(a["href"]):
            links.append({"text": t, "href": urljoin(r.url, a["href"])[:250]})
    res["job_links"] = links[:25]
    follow = []  # one level down: pages linked as careers/jobs on the same or a jobs host
    for lk in links:
        h = lk["href"]
        if h.startswith("http") and h not in follow and h != r.url and not h.lower().endswith((".pdf", ".docx")):
            follow.append(h)
        if len(follow) >= 4:
            break
    res["followed"] = []
    for h in follow:
        try:
            rr = http.get(h, allow_redirects=True)
            res["followed"].append({"url": h, "final": rr.url, "status": rr.status_code, "ats": _fingerprint(rr.text)})
        except RobotsBlocked as e:
            res["followed"].append({"url": h, "status": "robots", "note": str(e)[:150]})
        except Exception as e:
            res["followed"].append({"url": h, "status": "error", "note": f"{type(e).__name__}: {str(e)[:150]}"})
    return res


def read_brimr(url):
    from openpyxl import load_workbook  # installed only in the probe workflow
    data = Http().get(url).content
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    lines = [f"source: {url}"]
    for ws in wb.worksheets:
        lines.append(f"## sheet {ws.title}")
        for row in ws.iter_rows(values_only=True):
            cells = ["" if c is None else str(c).strip() for c in row]
            if any(cells):
                lines.append(" | ".join(cells))
    return "\n".join(lines) + "\n"


def run_candidates(only):
    sources = run.load_yaml("sources.yaml")
    try:
        cand = run.load_yaml("probe_sources.yaml") or {"schools": []}
    except FileNotFoundError:
        cand = {"schools": []}
    profile = run.load_yaml("profile.yaml")
    rules = Rules(profile)
    run.MAX_NEW_DETAILS_PER_SOURCE = 3  # a probe only needs to see that detail pages can be read
    pool_ = cand["schools"] if not only else sources["schools"] + cand["schools"]
    tasks = [(s, src) for s in pool_ for src in s["sources"] if not only or src["id"] in only]
    today = run.datetime.now(run.timezone.utc).strftime("%Y-%m-%d")
    report = []

    def one(t):
        school, src = t
        out, health, too_old = run.run_source(school, src, profile, rules, {}, today, {})
        health["candidate_titles"] = [r["title"] for r in out.values()][:15]
        health["candidate_samples"] = [{"title": r["title"], "url": r["url"], "posted": r["posted"],
                                        "dept": r["department"], "text": (r.get("_description") or "")[:300]}
                                       for r in out.values() if r.get("_description")][:3]
        health["too_old_count"] = len(too_old)
        return health

    with ThreadPoolExecutor(max_workers=8) as pool:
        report = list(pool.map(one, tasks))
    return report


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--brimr", default="")
    ap.add_argument("--sites", default="")
    ap.add_argument("--only", default=None)
    args = ap.parse_args(argv)
    OUT.mkdir(exist_ok=True)
    if args.brimr:
        (OUT / "brimr.txt").write_text(read_brimr(args.brimr), encoding="utf-8")
    if args.sites:
        rows = []
        for line in Path(args.sites).read_text(encoding="utf-8").splitlines():
            if "|" in line and not line.lstrip().startswith("#"):
                label, url = [x.strip() for x in line.split("|", 1)]
                rows.append((label, url))
        with ThreadPoolExecutor(max_workers=8) as pool:
            res = list(pool.map(lambda r: probe_site(Http(), *r), rows))
        (OUT / "sites.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    if args.only is not None:
        only = {s for s in args.only.split(",") if s}
        (OUT / "sources.json").write_text(json.dumps(run_candidates(only), indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
