"""Rule checks on real postings captured 2026-10-23 (trimmed)."""
import json
from pathlib import Path

import yaml

from tracker.connectors import jibe, mcloud, workday, oracle, html_list
from tracker.rules import Rules

ROOT = Path(__file__).resolve().parent.parent
FX = Path(__file__).parent / "fixtures"
RULES = Rules(yaml.safe_load((ROOT / "config" / "profile.yaml").read_text()))


def fx(name):
    return json.loads((FX / name).read_text())


def test_title_gate():
    ok = ["Postdoctoral Research Associate - Hematology", "RESEARCH FELLOW", "Clinical Research Coordinator 2",
          "(Clinical) Research Associate ", "Post Doctoral Fellow-MSH-32015-001", "Postgraduate Associate",
          "Associate in Research", "Research Project Coordinator (Pediatrics)"]
    bad = ["Clinical Nurse (Pulmonary)", "Research Technologist (Department of Medicine- Infectious Diseases)",
           "Director of Development, Johns Hopkins Medicine", "Clinical Research Manager", "Assistant Professor",
           "Pharmacist I/II - Inpatient - Hillcrest - 141924", "Hospitalist Physician - Pediatric Cardiac Critical Care"]
    for t in ok:
        assert RULES.title_ok(t), t
    for t in bad:
        assert not RULES.title_ok(t), t


def test_nyu_dialysis_research_is_clinical_nephrology():
    job = mcloud.parse_list(fx("mcloud.json"), {"id": "nyu"})[0][0]
    ev = RULES.evaluate(job)
    assert ev["research_type"] == "Clinical or dry research", ev
    assert ev["division"] == "Nephrology", ev
    # Division comes from the description, not a department field, so rules alone ask for a look.
    assert ev["verdict"] == "Check", ev


def test_department_field_decides():
    from tracker.models import Job
    clinical = "Clinical research with patients, IRB, REDCap data management, cohort analysis."
    peds = Job("duke", "1", "Postdoctoral Associate", "u", department="Pediatrics-Rheumatology", description=clinical)
    assert RULES.evaluate(peds)["verdict"] == "Other dept"
    onc = Job("duke", "2", "Postdoctoral Associate", "u", department="Medicine - Oncology", description=clinical)
    ev = RULES.evaluate(onc)
    assert ev["verdict"] == "Match" and ev["division"] == "Hematology & Oncology", ev
    epi = Job("umich", "3", "RESEARCH FELLOW", "u", department="Epidemiology Department", description=clinical)
    assert RULES.evaluate(epi)["verdict"] == "Other dept"


def test_sinai_transplant_mouse_postdoc_is_wet_lab():
    jobs, _ = jibe.parse_list(fx("jibe.json"), {"id": "ms", "host": "careers.mountsinai.org"})
    ev = RULES.evaluate(jobs[0])
    assert ev["research_type"] == "Wet lab" and ev["verdict"] == "Excluded", ev


def test_sinai_health_services_postdoc_is_dry():
    jobs, _ = jibe.parse_list(fx("jibe.json"), {"id": "ms", "host": "careers.mountsinai.org"})
    ev = RULES.evaluate(jobs[1])
    assert ev["research_type"] == "Clinical or dry research", ev
    assert ev["verdict"] == "Other dept", ev  # Center for Child Health Services Research


def test_sinai_wet_lab_division_read_from_department_line():
    jobs, _ = jibe.parse_list(fx("jibe.json"), {"id": "ms", "host": "careers.mountsinai.org"})
    assert RULES.evaluate(jobs[0])["division"] == "Nephrology"


def test_washu_cryoem_postdoc_is_wet_lab():
    src = {"id": "wustl", "host": "wustl.wd1.myworkdayjobs.com", "tenant": "wustl", "site": "External"}
    job = workday.parse_list(fx("workday_list.json"), src)[0][0]
    workday.parse_detail(fx("workday_detail.json"), job)
    ev = RULES.evaluate(job)
    assert ev["verdict"] == "Excluded" and ev["research_type"] == "Wet lab", ev


def test_stanford_crc_without_department_needs_a_look():
    src = {"id": "stanford", "host": "careersearch.stanford.edu", "site": "stanford"}
    job = oracle.parse_list(fx("oracle_list.json"), src)[0][0]
    oracle.parse_detail(fx("oracle_detail.json"), job)
    ev = RULES.evaluate(job)
    assert ev["research_type"] == "Clinical or dry research", ev
    assert ev["verdict"] == "Check", ev  # department not stated in the posting


def test_eligibility_flags():
    _, notes = RULES.eligibility("Applicants must be a U.S. citizen. PhD required.")
    assert "US citizenship or permanent residency mentioned" in notes
    assert "PhD appears required with no MD alternative" in notes
    _, notes = RULES.eligibility("MD or PhD required. We will sponsor J-1 visas.")
    assert notes == ["Visa sponsorship mentioned"]
    flags, notes = RULES.eligibility("The department is unable to sponsor visas for this position.")
    assert flags["no_sponsorship"]


def test_review_regressions():
    from tracker.models import Job
    clinical = "Clinical research with patients, IRB approval, REDCap data management and cohort analysis."
    imaging = Job("x", "1", "Research Associate", "u", department="Center for Biomedical Imaging", description=clinical)
    assert RULES.evaluate(imaging)["division"] != "Geriatrics & Palliative"
    env = Job("x", "2", "Research Associate", "u", department="Department of Medicine - Cardiology",
              description="A collaborative work environment. " + clinical)
    assert RULES.evaluate(env)["verdict"] == "Match"
    _, notes = RULES.eligibility("Location: Baltimore, MD 21205. PhD required in molecular biology.")
    assert "PhD appears required with no MD alternative" in notes
    _, notes = RULES.eligibility("MD or PhD required.")
    assert "PhD appears required with no MD alternative" not in notes
    cardio = Job("x", "3", "Research Fellow", "u", department="Internal Medicine - Cardiology", description=clinical)
    assert RULES.evaluate(cardio)["division"] == "Cardiology"
