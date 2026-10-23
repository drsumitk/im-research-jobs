"""Parser tests against trimmed copies of real responses captured on 2026-10-23."""
import json
from datetime import date
from pathlib import Path

from tracker.connectors import workday, oracle, eightfold, rmk, jibe, mcloud, taleo, html_list, ucrecruit
from tracker.models import Job

FX = Path(__file__).parent / "fixtures"


def load(name):
    p = FX / name
    return json.loads(p.read_text()) if name.endswith(".json") else p.read_text()


def test_workday_list_and_detail():
    src = {"id": "wustl", "host": "wustl.wd1.myworkdayjobs.com", "tenant": "wustl", "site": "External"}
    jobs, total = workday.parse_list(load("workday_list.json"), src, today=date(2026, 10, 23))
    assert total == 54 and len(jobs) == 2
    j = jobs[0]
    assert j.job_id == "JR97187"
    assert j.url == "https://wustl.wd1.myworkdayjobs.com/External/job/Washington-University-Medical-Campus/Postdoctoral-Research-Associate---Biochemistry_JR97187"
    assert j.posted == "30+ days ago"
    workday.parse_detail(load("workday_detail.json"), j)
    assert "cryo-EM" in j.description and j.posted == "2026-09-01"
    assert "&#xa;" not in j.description


def test_workday_relative_dates():
    d = date(2026, 10, 23)
    assert workday.posted_from_text("Posted Today", d) == "2026-10-23"
    assert workday.posted_from_text("Posted Yesterday", d) == "2026-10-22"
    assert workday.posted_from_text("Posted 14 Days Ago", d) == "2026-10-09"


def test_myworkdaysite_url():
    src = {"id": "penn", "host": "wd1.myworkdaysite.com", "tenant": "upenn", "site": "careers-at-penn"}
    jobs, _ = workday.parse_list({"total": 1, "jobPostings": [{"title": "X", "externalPath": "/job/A/X_JR1", "bulletFields": ["JR1"]}]}, src)
    assert jobs[0].url == "https://wd1.myworkdaysite.com/recruiting/upenn/careers-at-penn/job/A/X_JR1"


def test_oracle():
    src = {"id": "stanford", "host": "careersearch.stanford.edu", "site": "stanford"}
    jobs, total = oracle.parse_list(load("oracle_list.json"), src)
    assert total == 265 and jobs[0].job_id == "201445" and jobs[0].posted == "2026-10-22"
    assert jobs[0].url.endswith("/sites/stanford/job/201445")
    oracle.parse_detail(load("oracle_detail.json"), jobs[0])
    assert "subject recruitment" in jobs[0].description


def test_eightfold():
    src = {"id": "jhu", "host": "hiring.jhu.edu", "domain": "jhu.edu"}
    jobs, total = eightfold.parse_list(load("eightfold_search.json"), src)
    assert total == 359 and jobs[0].job_id == "122857" and jobs[0].posted == "2026-10-23"
    eightfold.parse_detail(load("eightfold_detail.json"), jobs[0])
    assert "fundraising" in jobs[0].description
    assert jobs[0].url == "https://hiring.jhu.edu/careers/job/1133916425530"


def test_rmk():
    src = {"id": "duke", "host": "careers.duke.edu"}
    jobs, total = rmk.parse_list(load("rmk_search.html"), src)
    assert total == 39 and len(jobs) == 3
    assert jobs[2].department == "Medicine - Oncology" and jobs[2].posted == "2026-10-22"
    rmk.parse_detail(load("rmk_detail.html"), jobs[0])
    assert "agent-based models" in jobs[0].description and jobs[0].posted == "2026-10-23"


def test_jibe():
    src = {"id": "mountsinai", "host": "careers.mountsinai.org"}
    jobs, total = jibe.parse_list(load("jibe.json"), src)
    assert total == 236 and len(jobs) == 2
    assert jobs[0].url == "https://careers.mountsinai.org/jobs/3043330?lang=en-us"
    assert "Flow-cytometry" in jobs[0].description and jobs[0].posted == "2026-10-13"


def test_mcloud():
    src = {"id": "nyulangone", "organization": 1637}
    jobs, total = mcloud.parse_list(load("mcloud.json"), src)
    assert total == 12 and jobs[0].url.startswith("https://jobs.nyulangone.org/job/23935102/")
    assert "not include bench science" in jobs[0].description


def test_taleo():
    src = {"id": "cu-anschutz", "host": "cu.taleo.net", "section": "2"}
    jobs, total, size = taleo.parse_list(load("taleo_search.json"), src)
    assert total == 598 and size == 25 and jobs[1].title == "Postdoctoral Fellow/Trainee"
    assert jobs[1].location == "Aurora"
    assert jobs[1].url == "https://cu.taleo.net/careersection/2/jobdetail.ftl?job=40576&lang=en"
    taleo.parse_detail(load("taleo_detail.html"), jobs[0])
    assert "Department of Family Medicine" in jobs[0].description
    assert "Job Summary:" in jobs[0].description


def test_html_list_ldjson():
    src = {"id": "ucsd", "host": "employment.ucsd.edu", "link_pattern": "/job/[0-9A-F]{32}$", "detail": "ldjson"}
    jobs = html_list.parse_list(load("htmlld_search.html"), src)
    assert [j.title for j in jobs] == ["Clinical Research Coordinator II - Cancer Center - 140008",
                                       "Linen Service Worker - La Jolla - 141882"]
    html_list.parse_detail(load("htmlld_detail.html"), jobs[0], src)
    assert jobs[0].posted == "2026-10-23" and jobs[0].department == "CANCER CENTER/Clinical Trials Office"
    assert jobs[0].location == "San Diego, CA"


def test_html_list_css():
    src = {"id": "umich", "host": "careers.umich.edu", "link_pattern": r"^/job_detail/\d+/",
           "detail": "css", "detail_selector": ".layout-content"}
    jobs = html_list.parse_list(load("umich_search.html"), src)
    assert jobs[0].title == "RESEARCH FELLOW" and jobs[0].posted == "2026-10-23"
    assert jobs[0].department == "Epidemiology Department"
    html_list.parse_detail(load("umich_detail.html"), jobs[0], src)
    assert "LASI-DAD" in jobs[0].description


def test_ucrecruit():
    src = {"id": "ucla-recruit", "host": "recruit.apo.ucla.edu"}
    jobs = ucrecruit.parse_feed(load("ucrecruit.atom"), src)
    assert jobs[0].job_id == "JPF11346" and jobs[0].posted == "2026-09-16"
    assert "Anesthesiology" in jobs[0].description


def test_taleo_posting_date():
    src = {"id": "cu-anschutz", "host": "cu.taleo.net", "section": "2"}
    jobs, _, _ = taleo.parse_list(load("taleo_search.json"), src)
    taleo.parse_detail(load("taleo_detail.html"), jobs[0])
    assert jobs[0].posted == "2026-07-20"


def test_smartrecruiters():
    from tracker.connectors import smartrecruiters
    src = {"id": "harvard", "company": "HarvardUniversity"}
    jobs, total = smartrecruiters.parse_list(load("smartrecruiters_list.json"), src)
    assert total == 12 and jobs[0].posted == "2026-10-22" and jobs[0].department == "HBS AI Institute"
    smartrecruiters.parse_detail(load("smartrecruiters_detail.json"), jobs[0])
    assert "research compliance" in jobs[0].description
    assert jobs[0].url.startswith("https://jobs.smartrecruiters.com/HarvardUniversity/3743990016333246")
