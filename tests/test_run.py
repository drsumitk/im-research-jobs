import yaml
from pathlib import Path

from tracker import run, classify

run.AI_GAP_SECONDS = 0

PROFILE = yaml.safe_load((Path(__file__).resolve().parent.parent / "config" / "profile.yaml").read_text())


def rec(key):
    return {"key": key, "source": "s", "title": "Research Fellow", "url": "u", "location": "", "department": "",
            "posted": "", "ai": None, "_description": "clinical outcomes research text " * 10,
            "verdict": "Check", "reason": "r"}


def test_ai_overrides_rules_and_respects_budget(monkeypatch):
    monkeypatch.setattr(classify, "available", lambda: True)
    calls = []

    def fake(job, profile, session=None, **kw):
        calls.append(job.title)
        return {"verdict": "match", "reason": "clinical outcomes, Cardiology", "im_division": "Cardiology"}

    monkeypatch.setattr(classify, "classify", fake)
    prof = dict(PROFILE, ai=dict({k: v for k, v in PROFILE["ai"].items() if k != "review_model"}, max_calls_per_run=2))
    records = {k: rec(k) for k in ("a", "b", "c")}
    log = []
    used = run.apply_ai(records, prof, log)
    assert used == 2 and len(calls) == 2
    assert [r["verdict"] for r in records.values()].count("Match") == 2
    assert any("budget" in line for line in log)


def test_ai_off_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    log = []
    assert run.apply_ai({"a": rec("a")}, PROFILE, log) == 0
    assert "off" in log[0]


def test_failed_ai_attempts_are_capped(monkeypatch):
    monkeypatch.setattr(classify, "available", lambda: True)

    def boom(job, profile, session=None, **kw):
        raise RuntimeError("Claude API HTTP 401: invalid")

    monkeypatch.setattr(classify, "classify", boom)
    r = rec("a")
    for _ in range(5):
        run.apply_ai({"a": r}, PROFILE, [])
    assert r["ai_attempts"] == run.MAX_AI_ATTEMPTS
    log = []
    run.apply_ai({"a": rec("b")}, PROFILE, log)
    assert "401" not in " ".join(log)  # error detail stays out of the public page


def test_recency_window():
    t = "2026-10-24"
    assert run.is_recent("2026-10-10", t, 21)
    assert not run.is_recent("2026-02-18", t, 21)          # the Mount Sinai example
    assert not run.is_recent("30+ days ago", t, 21)        # Workday list text
    assert run.is_recent("", t, 21)                        # unknown date: keep, judge later
    assert run.is_recent("2026-02-18", t, None)            # window switched off


def test_old_posting_found_on_detail_page_is_remembered_and_not_reopened(monkeypatch):
    from tracker.models import Job
    from tracker.rules import Rules

    opened = []

    class FakeConnector:
        @staticmethod
        def search(http, src, terms, title_ok):
            return [Job("s", "1", "Postdoctoral Fellow", "https://x/1")]  # list page has no date

        @staticmethod
        def details(http, src, job):
            opened.append(job.key)
            job.description, job.posted = "Department: Medicine", "2026-07-20"
            return job

    monkeypatch.setitem(run.REGISTRY, "fake", FakeConnector)
    school, src = {"name": "X", "rank": 1}, {"id": "s", "type": "fake"}
    rules, today = Rules(PROFILE), "2026-10-24"
    out, health, old = run.run_source(school, src, PROFILE, rules, {}, today)
    assert out == {} and "s:1" in old and health["too_old"] == 1 and health["candidates"] == 0
    # Next day: a stale copy without a date exists in the saved state; it must not be reopened or kept.
    state = {"s:1": {"key": "s:1", "posted": "", "evaluated": True, "ai": {"verdict": "check"}}}
    out, health, old2 = run.run_source(school, src, PROFILE, rules, state, today, skipped=old)
    assert out == {} and opened == ["s:1"] and "s:1" in old2


def test_undated_postings_expire_after_window_from_first_seen():
    assert run.age_basis("", "2026-09-01", "2026-10-24") == "2026-09-01"
    assert not run.is_recent(run.age_basis("", "2026-09-01", "2026-10-24"), "2026-10-24", 21)
    assert run.is_recent(run.age_basis("", None, "2026-10-24"), "2026-10-24", 21)   # first seen today
    assert run.age_basis("2026-10-20", "2026-01-01", "2026-10-24") == "2026-10-20"  # a real date wins


def test_borderline_verdicts_get_one_review_by_the_stronger_model(monkeypatch):
    monkeypatch.setattr(classify, "available", lambda: True)
    calls = []

    def fake(job, profile, session=None, model=None, **kw):
        calls.append(model or "first")
        if model:
            return {"verdict": "match", "reason": "review: clinical outcomes in Cardiology"}
        return {"verdict": "check" if job.title == "Research Fellow" else "excluded", "reason": "first pass"}

    monkeypatch.setattr(classify, "classify", fake)
    prof = dict(PROFILE, ai=dict(PROFILE["ai"], review_model="claude-sonnet-5-5", max_review_calls_per_run=5))
    records = {"a": rec("a"), "b": dict(rec("b"), title="Postdoc lab")}
    used = run.apply_ai(records, prof, [])
    assert calls == ["first", "first", "claude-sonnet-5-5"] and used == 3
    a = records["a"]
    assert a["verdict"] == "Match" and a["ai_first"]["verdict"] == "check" and a["ai_review_done"]
    assert records["b"]["verdict"] == "Excluded" and "ai_first" not in records["b"]
    run.apply_ai(records, prof, [])  # nothing left to do on a later run
    assert len(calls) == 3


def test_review_switched_off_without_review_model(monkeypatch):
    monkeypatch.setattr(classify, "available", lambda: True)
    monkeypatch.setattr(classify, "classify", lambda job, profile, session=None, model=None, **kw:
                        {"verdict": "check", "reason": "x"})
    prof = dict(PROFILE, ai={k: v for k, v in PROFILE["ai"].items() if k != "review_model"})
    records = {"a": rec("a")}
    assert run.apply_ai(records, prof, []) == 1 and "ai_first" not in records["a"]


def test_title_only_postings_are_flagged_and_department_rule_skips_ai(monkeypatch):
    monkeypatch.setattr(classify, "available", lambda: True)
    seen = []
    monkeypatch.setattr(classify, "classify", lambda job, profile, session=None, model=None, **kw:
                        seen.append(kw.get("title_only")) or {"verdict": "match", "reason": "x", "confidence": "low"})
    short = dict(rec("a"), _description="Department: MD-PULMONARY MEDICINE\nPostdoctoral Associate - Pulmonary")
    outside = dict(rec("b"), skip_ai=True, verdict="Other dept")
    run.apply_ai({"a": short, "b": outside}, PROFILE, [])
    assert seen[0] is True and outside["verdict"] == "Other dept" and not outside.get("ai")


def test_match_with_weak_skills_fit_is_a_stretch():
    assert run.verdict_of({"verdict": "match", "skills_fit": "weak"}) == "Stretch"
    assert run.verdict_of({"verdict": "match", "skills_fit": "partial"}) == "Match"
    assert run.verdict_of({"verdict": "excluded", "skills_fit": "weak"}) == "Excluded"


def test_old_reviews_are_redone_after_instructions_change():
    prof = dict(PROFILE, ai=dict(PROFILE["ai"], review_model="m", review_verdicts=["check", "match"]))
    done_old = {"ai": {"verdict": "match"}, "ai_review_done": True, "review_version": 1}
    done_new = dict(done_old, review_version=run.REVIEW_VERSION)
    assert run.needs_review(done_old, prof) and not run.needs_review(done_new, prof)
    assert not run.needs_review({"ai": {"verdict": "excluded"}}, prof)


def test_match_grouping_rules_from_the_audit():
    m = {"verdict": "match", "role_type": "postdoc", "confidence": "medium", "skills_fit": "strong",
         "mbbs_without_phd_eligible": "yes"}
    assert run.verdict_of(m) == "Match"
    assert run.verdict_of(dict(m, role_type="research_assistant")) == "Below level"   # e.g. peer recovery assistant
    assert run.verdict_of(dict(m, mbbs_without_phd_eligible="no")) == "Excluded"      # e.g. 3 years postdoc required
    assert run.verdict_of(dict(m, confidence="low")) == "Check"                       # generic posting
    assert run.verdict_of(dict(m, skills_fit="weak")) == "Stretch"                    # e.g. econometrics minimum


def test_undecided_posting_naming_a_pi_gets_one_lab_lookup(monkeypatch):
    monkeypatch.setattr(classify, "available", lambda: True)
    lookups = []
    monkeypatch.setattr(classify, "classify", lambda job, profile, session=None, model=None, **kw:
                        {"verdict": "check", "reason": "no lab details", "confidence": "low"})

    def fake_lookup(job, profile, school, session=None, model=None):
        lookups.append(job.title)
        return {"verdict": "excluded", "reason": "Lab papers are mouse CAR-T work.", "research_type": "wet_lab",
                "pi": "A B", "lab_summary": "CAR-T", "lab_sources": [], "searches": 2, "confirmed": True}

    monkeypatch.setattr(classify, "lab_lookup", fake_lookup)
    records = {"a": dict(rec("a"), title="Research Fellow with Dr Sakemura", school="Mayo Clinic"),
               "b": rec("b")}
    run.apply_ai(records, PROFILE, [])
    a = records["a"]
    assert lookups == ["Research Fellow with Dr Sakemura"]
    assert a["verdict"] == "Excluded" and a["ai_before_lookup"]["verdict"] == "check"
    assert a["lookup"]["searches"] == 2 and a["lookup"]["by"] == PROFILE["ai"]["lookup_label"]
    assert records["b"]["verdict"] == "Check" and "lookup" not in records["b"]
    run.apply_ai(records, PROFILE, [])
    assert len(lookups) == 1  # looked up once only


def test_title_only_posting_is_searched_once_then_goes_to_title_only_tab(monkeypatch):
    monkeypatch.setattr(classify, "available", lambda: True)
    monkeypatch.setattr(classify, "classify", lambda job, profile, session=None, model=None, **kw:
                        {"verdict": "check", "reason": "title only", "confidence": "low"})
    finds = []

    def fake_find(job, profile, school, session=None, model=None):
        finds.append(job.title)
        if job.title == "Postdoctoral Associate - Pulmonary":
            return {"verdict": "match", "reason": "ICU cohorts", "confidence": "medium", "role_type": "postdoc",
                    "searches": 2, "copy": {"url": "https://c", "title": "t", "kind": "secondary",
                                            "match": "job_id", "excerpt": "e", "_text": "full copy text"}}
        return {"verdict": "check", "reason": "no copy", "confidence": "low", "copy": None, "searches": 3}

    monkeypatch.setattr(classify, "find_posting", fake_find)
    monkeypatch.setattr(classify, "lab_lookup", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no PI")))
    short = lambda k, t: dict(rec(k), title=t, _description="Department: MD-PULMONARY", school="Florida")
    records = {"a": short("a", "Postdoctoral Associate - Pulmonary"), "b": short("b", "Postdoctoral Researcher"),
               "c": rec("c")}
    run.apply_ai(records, PROFILE, [])
    assert records["a"]["verdict"] == "Match" and records["a"]["copy"]["kind"] == "secondary"
    assert "_text" not in records["a"]["copy"] and records["a"]["ai_before_find"]["verdict"] == "check"
    assert records["b"]["verdict"] == "Title only" and records["b"]["find_version"] == run.FIND_VERSION
    assert records["c"]["verdict"] == "Check"  # full text was read: stays in Needs a look
    run.apply_ai(records, PROFILE, [])
    assert len(finds) == 2  # each title-only posting is searched once
