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


def test_sitemap_harvard():
    from tracker.connectors import sitemap
    src = {"id": "harvard", "sitemap_url": "https://careers.harvard.edu/vacanciessitemap.xml"}
    jobs = sitemap.parse_sitemap(load("sitemap_list.xml"), src)
    assert [j.job_id for j in jobs] == ["292", "1888", "2240", "2317"]
    assert jobs[2].title == "research assistant iii non lab" and jobs[2].posted == "2026-09-28"
    assert jobs[1].title == "research associate writing focused division of research and faculty development"
    sitemap.parse_detail(load("sitemap_detail.html"), jobs[2])
    j = jobs[2]
    assert j.title == "Research Assistant III Non-Lab" and j.posted == "2026-09-28"
    assert j.department == "Harvard Medical School / Global Health and Social Medicine"
    assert j.description.startswith("Department: Global Health and Social Medicine")
    assert "Mental Health for All Lab" in j.description and j.location == "Boston, MA, United States"


def test_board_yale_time_and_link():
    from tracker.connectors import board
    src = {"id": "yale-postdoc", "url": "https://postdocs.yale.edu/applicants/open-positions?page={page}",
           "row": "li.reference-card", "link": "a.reference-card__heading-link", "detail": ".text-field"}
    jobs = board.parse_list(load("board_yale.html"), src, "https://postdocs.yale.edu/applicants/open-positions?page=0")
    assert len(jobs) == 2 and jobs[1].posted == "2026-10-20"
    assert "Internal Medicine" in jobs[1].title
    assert jobs[1].url == ("https://postdocs.yale.edu/posts/2026-10-20-postdoctoral-associate-position-in-"
                           "pharmaceutical-regulation-and-evidence")


def test_board_stanford_caption_template_and_dedupe():
    from tracker.connectors import board
    src = {"id": "stanford-postdoc", "row": "table.views-table tr",
           "link": 'a[href*="/prospective/opportunities/"]', "title": "p strong",
           "title_template": "Postdoctoral {title}", "dept_caption": True}
    jobs = board.parse_list(load("board_stanford.html"), src, "https://postdocs.stanford.edu/prospective/opportunities")
    assert len(jobs) == 2 and jobs[0].key == jobs[1].key  # same opening listed under two departments
    j = jobs[0]
    assert j.title == "Postdoctoral Position with Louise Sun" and j.posted == "2026-09-04"
    assert j.department == "Anesthesiology, Perioperative and Pain Medicine"


def test_board_vanderbilt_cells_and_relative_link():
    from tracker.connectors import board
    src = {"id": "vanderbilt-postdoc", "row": 'tr:has(a[href^="?id="])', "link": 'a[href^="?id="]',
           "date": "td:nth-of-type(1)", "dept": "td:nth-of-type(2)", "mentor": "td:nth-of-type(4)",
           "title_template": "Postdoctoral position: {dept} ({mentor})"}
    base = "https://www.vanderbilt.edu/postdoc/prospective-postdocs/current-opportunities/"
    [j] = board.parse_list(load("board_vanderbilt.html"), src, base)
    assert j.url == base + "?id=954" and j.posted == "2026-10-16"
    assert j.title == "Postdoctoral position: Biological Sciences (Carl Johnson and Alexandre Tiriac)"


def test_board_wcm_dotted_date():
    from tracker.connectors import board
    src = {"id": "wcm", "row": 'tr:has(a[href*="/opportunities/postdoctoral-positions/"])',
           "link": 'a[href*="/opportunities/postdoctoral-positions/"]', "date": "td.views-field-created",
           "dept": "td.views-field-field-department", "mentor": "td.views-field-field-faculty-name"}
    [j] = board.parse_list(load("board_wcm.html"), src, "https://postdocs.weill.cornell.edu/opportunities/postdoctoral-positions")
    assert j.posted == "2026-10-19" and j.department == "Appel Institute/BMRI"
    assert j.title.startswith("Postdoctoral Associate in Neuroscience")


def test_board_rochester_rows_without_links():
    from tracker.connectors import board
    src = {"id": "rochester-postdoc", "row": "table tr:has(td)", "date": "td:nth-of-type(1)",
           "mentor": "td:nth-of-type(2)", "dept": "td:nth-of-type(3)",
           "title_template": "Postdoctoral position: {dept} ({mentor})", "detail": "none"}
    url = "https://www.urmc.rochester.edu/education/post-doctoral/post-doctoral-positions"
    jobs = board.parse_list(load("board_rochester.html"), src, url)
    assert len(jobs) == 2 and jobs[0].key != jobs[1].key and jobs[1].url == url
    assert jobs[1].title == "Postdoctoral position: Hematology and Oncology (Naoko Takebe)"
    assert jobs[1].posted == "2026-09-25" and jobs[1].description.startswith("Department: Hematology and Oncology")


def test_board_iowa_detail_date_label():
    from tracker.connectors import board
    src = {"id": "iowa-postdoc", "row": 'tr:has(a[href*="/postdoc/view/"])', "link": 'a[href*="/postdoc/view/"]',
           "dept": "td:nth-of-type(4)", "date": "none", "detail": "body",
           "detail_date_label": "Advertising Started on:"}
    [j] = board.parse_list(load("board_iowa_list.html"), src, "https://jobs.uiowa.edu/jobSearch/postdoc/searchResults.php")
    assert j.posted == "" and j.department == "Internal Medicine" and j.url == "https://jobs.uiowa.edu/postdoc/view/4528"
    board.parse_detail(load("board_iowa_detail.html"), j, src)
    assert j.posted == "2025-12-22" and "Hematology/Oncology" in j.description


def test_icims_list_and_detail():
    from tracker.connectors import icims
    src = {"id": "umasschan", "host": "careers-umms.icims.com"}
    jobs = icims.parse_list(load("icims_list.html"), src)
    assert [j.job_id for j in jobs] == ["51863", "42216"]
    assert jobs[0].title == "Post Doc - Open Rank" and jobs[0].posted == "2026-08-17"
    assert jobs[0].department == "Biochem & Molecular Biotech" and jobs[0].url.endswith("/jobs/51863/post-doc---open-rank/job")
    assert jobs[1].posted == "" and jobs[1].department.startswith("Institute on Development")
    icims.parse_detail(load("icims_detail.html"), jobs[0])
    assert jobs[0].description.startswith("Department: Biochem") and "registry data" in jobs[0].description


def test_find_date_formats():
    from tracker.textutil import find_date
    assert find_date("Posted on: September 04, 2026") == "2026-09-04"
    assert find_date("Advertising Started on: Monday, December 22nd, 2025") == "2025-12-22"
    assert find_date("Advertised: 21 Oct 2026 Eastern") == "2026-10-21"
    assert find_date("10.19.2026") == "2026-10-19" and find_date("2026-10-20T00:00") == "2026-10-20"
    assert find_date("$62,232.00 to Commensurate") == ""


def test_sitemap_title_strip():
    from tracker.connectors.sitemap import title_from_slug
    s = "postdoctoral-research-associate-medicine-madison-wisconsin-united-states-270034a7-6177"
    assert title_from_slug(s, "-madison-wisconsin-united-states.*$") == "postdoctoral research associate medicine"


def test_board_search_terms_and_bilh_cards():
    from tracker.connectors import board
    src = {"id": "bilh", "url": "https://jobs.bilh.org/jobs/?q={q}&city=&sort=date_desc", "row": "article.job-card",
           "link": "h2 a", "location": "p.muted"}
    assert board._page_urls(src, ["post doc", "research fellow"]) == [
        "https://jobs.bilh.org/jobs/?q=post+doc&city=&sort=date_desc",
        "https://jobs.bilh.org/jobs/?q=research+fellow&city=&sort=date_desc"]
    [j] = board.parse_list(load("board_bilh.html"), src, "https://jobs.bilh.org/jobs/?q=postdoctoral")
    assert j.title == "Postdoctoral research fellow" and j.posted == "2026-10-22"
    assert j.url == "https://jobs.bilh.org/jobs/postdoctoral-research-fellow-boston-ma-jr105863/"
    assert j.location.startswith("Boston, MA • Beth Israel Deaconess Medical Center")


def test_phenom_list_and_detail():
    from tracker.connectors import phenom
    src = {"id": "bswhealth", "host": "jobs.bswhealth.com", "path": "/us/en"}
    jobs, total = phenom.parse_list(load("phenom_list.json"), src)
    assert total == 3 and jobs[1].title == "Research Analyst 2" and jobs[1].posted == "2026-10-22"
    assert jobs[1].url == "https://jobs.bswhealth.com/us/en/job/26005020" and jobs[1].location == "Dallas, Texas"
    phenom.parse_detail(load("phenom_detail.html"), jobs[1])
    assert "outcomes research" in jobs[1].description


def test_board_houston_methodist_ldjson_date():
    from tracker.connectors import board
    src = {"id": "houstonmethodist", "row": 'div:has(> a[href^="/job/"])', "link": 'a[href^="/job/"]',
           "title": "h2", "date": "none", "detail": ".job-description", "detail_ldjson_date": True}
    base = "https://www.houstonmethodistcareers.org/jobs/postdoctoral-fellows/?radius=25"
    [j] = board.parse_list(load("board_houstonmethodist.html"), src, base)
    assert j.title == "Clinical Research Fellow 0" and j.posted == ""
    assert j.url.startswith("https://www.houstonmethodistcareers.org/job/116108/")
    board.parse_detail(load("board_houstonmethodist_detail.html"), j, src)
    assert j.posted == "2026-04-20" and "clinical research projects" in j.description


def test_board_mhif_distinct_ids_from_query_strings():
    from tracker.connectors import board
    src = {"id": "mhif", "row": 'div.field__item:has(a[href*="workforcenow.adp.com"])',
           "link": 'a[href*="workforcenow.adp.com"]', "title": "h3", "date": "none", "detail": "none"}
    jobs = board.parse_list(load("board_mhif.html"), src, "https://mplsheart.org/careers")
    assert [j.title for j in jobs] == ["Advanced Cardiology Research Scholar, CCAD", "Research Scholar, CCAD"]
    assert jobs[0].key != jobs[1].key and "jobId=588688" in jobs[0].url
