import yaml
from pathlib import Path

from tracker import run, classify

run.AI_GAP_SECONDS = 0

PROFILE = yaml.safe_load((Path(__file__).resolve().parent.parent / "config" / "profile.yaml").read_text())


def rec(key):
    return {"key": key, "source": "s", "title": "Research Fellow", "url": "u", "location": "", "department": "",
            "posted": "", "ai": None, "_description": "text", "verdict": "Check", "reason": "r"}


def test_ai_overrides_rules_and_respects_budget(monkeypatch):
    monkeypatch.setattr(classify, "available", lambda: True)
    calls = []

    def fake(job, profile, session=None):
        calls.append(job.title)
        return {"verdict": "match", "reason": "clinical outcomes, Cardiology", "im_division": "Cardiology"}

    monkeypatch.setattr(classify, "classify", fake)
    prof = dict(PROFILE, ai=dict(PROFILE["ai"], max_calls_per_run=2))
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

    def boom(job, profile, session=None):
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
