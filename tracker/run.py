"""Daily run: fetch each source, keep matching titles, read new postings, classify, save for the dashboard.

Usage:  python -m tracker.run            (normal run)
        python -m tracker.run --only duke,yale   (run selected source ids)
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

from . import classify
from .connectors import REGISTRY
from .http import Http, RobotsBlocked
from .rules import Rules

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data"
MAX_NEW_DETAILS_PER_SOURCE = 80
DROP_AFTER_DAYS = 60
DROP_AFTER_DAYS_FAILED_SOURCE = 120  # longer grace when the site itself could not be read
FORGET_SKIPPED_AFTER_DAYS = 30  # stop remembering a too-old posting once it is no longer listed
MAX_AI_ATTEMPTS = 3
AI_GAP_SECONDS = 1.0  # pause between Claude calls to stay under per-minute rate limits
SNIPPET_CHARS = 900
TITLE_ONLY_CHARS = 200  # postings with less text than this carry only a title and department line
REVIEW_VERSION = 5     # bump when the review instructions change, so undecided postings are reviewed again


def load_yaml(name):
    with open(ROOT / "config" / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def fingerprint(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def is_recent(posted, today, max_days):
    """True when the posting date is within max_days of today, or when the date is unknown."""
    if not max_days:
        return True
    p = (posted or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", p)
    if m:
        cutoff = datetime.strptime(today, "%Y-%m-%d") - timedelta(days=int(max_days))
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))) >= cutoff
    m = re.search(r"(\d+)\+?\s*days? ago", p, re.I)
    if m:
        return int(m.group(1)) < int(max_days)
    return True


def has_date(posted):
    p = (posted or "").strip()
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", p) or re.search(r"\d+\+?\s*days? ago", p, re.I))


def age_basis(posted, first_seen, today):
    """The posting date when the site gives one; otherwise the day the tracker first saw the posting,
    so undated postings are shown for at most the same window after they first appear."""
    return posted if has_date(posted) else (first_seen or today)


def run_source(school, src, profile, rules, state, today, skipped=None):
    """Returns (records_by_key, health_entry, too_old_by_key). Never raises.

    too_old_by_key lists postings whose exact date (read from a detail page) is outside the window,
    so later runs neither open them again nor carry an older copy of them forward."""
    skipped = skipped or {}
    too_old = {}
    health = {"school": school["name"], "rank": school["rank"], "source": src["id"],
              "label": src.get("label", src["id"]), "type": src["type"], "checked": today}
    if src["type"] == "manual" or src.get("enabled") is False:
        health.update(status="manual" if src["type"] == "manual" else "paused",
                      url=src.get("url", ""), note=src.get("reason", ""))
        return {}, health, too_old
    mod = REGISTRY[src["type"]]
    http = Http()
    out = {}
    try:
        found = mod.search(http, src, profile["search_terms"], rules.title_ok)
        max_age = profile.get("max_posting_age_days")
        titled = [j for j in found if rules.title_ok(j.title)]
        cands = [j for j in titled if is_recent(j.posted, today, max_age)]
        health.update(found=len(found), candidates=len(cands), too_old=len(titled) - len(cands))
        new_details, detail_errors, late_old = 0, 0, 0
        for job in cands:
            old = state.get(job.key)
            known = (skipped.get(job.key) or {}).get("posted") or \
                (age_basis(old.get("posted"), old.get("first_seen"), today) if old else "")
            if known and not is_recent(known, today, max_age):
                too_old[job.key] = {"posted": known, "seen": today}
                late_old += 1
                continue  # an exact date read earlier shows it is too old
            ai_pending = bool(old) and classify.available() and (
                (not old.get("ai") and int(old.get("ai_attempts", 0)) < MAX_AI_ATTEMPTS)
                or needs_review(old, profile))
            if old and old.get("evaluated") and not ai_pending:
                old["last_seen"] = today
                old["title"] = job.title or old["title"]
                out[job.key] = old
                continue
            if not job.description:
                if new_details >= MAX_NEW_DETAILS_PER_SOURCE:
                    if old:  # still listed today; keep it visible and finish it on a later run
                        old["last_seen"] = today
                        out[job.key] = old
                    continue  # new job: picked up on the next run
                try:
                    mod.details(http, src, job)
                    new_details += 1
                except Exception as e:  # keep going; one bad page must not stop the source
                    detail_errors += 1
                    health["last_detail_error"] = str(e)[:200]
            basis = age_basis(job.posted, (old or {}).get("first_seen"), today)
            if not is_recent(basis, today, max_age):
                too_old[job.key] = {"posted": basis, "seen": today}
                late_old += 1
                continue  # the detail page gave an exact date outside the window
            ev = rules.evaluate(job)
            dept_rule = src.get("department_must_match")
            outside = bool(dept_rule) and not re.search(dept_rule, job.department or "", re.I)
            if outside:
                ev = dict(ev, verdict="Other dept",
                          reason=f"Department {job.department or '(not stated)'} is outside the medical school.")
            out[job.key] = {
                "key": job.key, "school": school["name"], "rank": school["rank"],
                "source": src["id"], "source_label": src.get("label", src["id"]),
                "title": job.title, "url": job.url, "location": job.location,
                "department": job.department, "posted": job.posted,
                "first_seen": (old or {}).get("first_seen", today), "last_seen": today,
                "snippet": job.description[:SNIPPET_CHARS],
                "fingerprint": fingerprint(job.description),
                "rules": ev, "ai": None, "evaluated": bool(job.description),
                "ai_attempts": int((old or {}).get("ai_attempts", 0)),
                **{k: (old or {})[k] for k in ("ai", "ai_first", "review_attempts", "ai_review_done",
                                                "review_version", "reviewed_by") if (old or {}).get(k)},
                "verdict": ev["verdict"], "reason": ev["reason"],
                "_description": job.description,  # removed before saving
                **({"skip_ai": True} if outside else {}),
            }
            rec = out[job.key]
            if rec.get("ai"):  # re-opened only for the review pass: keep the first AI verdict meanwhile
                rec["verdict"] = verdict_of(rec["ai"]) if rec["ai"].get("verdict") in AI_TO_VERDICT \
                    else rec["verdict"]
                rec["reason"] = rec["ai"].get("reason", rec["reason"])
        health.update(status="ok", new_details=new_details, detail_errors=detail_errors,
                      candidates=len(cands) - late_old, too_old=len(titled) - len(cands) + late_old)
    except RobotsBlocked as e:
        health.update(status="blocked", error=str(e)[:300])
    except Exception as e:
        health.update(status="error", error=f"{type(e).__name__}: {str(e)[:300]}")
        traceback.print_exc()
    return out, health, too_old


AI_TO_VERDICT = {"match": "Match", "check": "Check", "other_dept": "Other dept", "excluded": "Excluded"}


def verdict_of(res):
    """Dashboard group for an AI result. A match is kept as a Match only when the AI is reasonably sure:
    a required skill the candidate lacks makes it a Stretch, an entry-level assistant job is Below level,
    and a low-confidence match goes to Needs a look."""
    v = AI_TO_VERDICT[res["verdict"]]
    if v != "Match":
        return v
    if res.get("mbbs_without_phd_eligible") == "no":
        return "Excluded"
    if res.get("role_type") in ("research_assistant", "clinical_research_coordinator", "other"):
        return "Below level"
    if res.get("skills_fit") == "weak":
        return "Stretch"
    if res.get("confidence") == "low":
        return "Check"
    return v


def needs_review(rec, profile):
    """A first-pass AI verdict in the review list that the review model has not yet re-checked."""
    ai = profile.get("ai", {})
    first = rec.get("ai") or {}
    if not ai.get("review_model") or int(rec.get("review_attempts", 0)) >= MAX_AI_ATTEMPTS + 1:
        return False
    wanted = set(ai.get("review_verdicts", ["check"]))
    if rec.get("ai_review_done"):
        # Reviewed under older instructions: review again if the posting is still in the review list.
        return int(rec.get("review_version", 1)) < REVIEW_VERSION and first.get("verdict") in wanted
    return first.get("verdict") in wanted


def _title_only(rec):
    return len(rec.get("_description") or "") < TITLE_ONLY_CHARS


def _job_of(rec):
    from .models import Job
    return Job(rec["source"], rec["key"], rec["title"], rec["url"], rec["location"],
               rec["department"], rec["posted"], rec["_description"])


def apply_ai(records, profile, log):
    """First pass: the main model (Haiku) classifies each new posting once.
    Second pass: the review model (Sonnet) re-checks postings the first pass left as borderline
    ("check" by default) and its verdict replaces the first one. Both passes have a per-run budget."""
    if not classify.available():
        log.append("AI classifier off (no ANTHROPIC_API_KEY secret).")
        return 0
    ai = profile.get("ai", {})
    budget = int(ai.get("max_calls_per_run", 150))
    used = errors = 0
    causes = Counter()
    for rec in records.values():
        if used >= budget:
            log.append(f"AI budget of {budget} calls reached; remaining jobs are classified on the next run.")
            break
        if rec.get("ai") or rec.get("skip_ai") or not rec.get("_description") \
                or int(rec.get("ai_attempts", 0)) >= MAX_AI_ATTEMPTS:
            continue
        rec["ai_attempts"] = int(rec.get("ai_attempts", 0)) + 1
        used += 1
        try:
            res = classify.classify(_job_of(rec), profile, title_only=_title_only(rec))
        except Exception as e:
            # Full detail goes to the private Actions log; the public page gets only the cause category.
            print(f"AI error on {rec['key']}: {e}", file=sys.stderr)
            errors += 1
            causes[getattr(e, "category", type(e).__name__)] += 1
            continue
        finally:
            time.sleep(AI_GAP_SECONDS)
        rec["ai"] = res
        rec["verdict"] = verdict_of(res)
        rec["reason"] = res.get("reason", "")

    review_model = ai.get("review_model")
    review_budget = int(ai.get("max_review_calls_per_run", 0))
    reviewed = 0
    if review_model and review_budget:
        for rec in records.values():
            if reviewed >= review_budget:
                log.append(f"Review budget of {review_budget} calls reached; remaining borderline postings "
                           "are re-checked on the next run.")
                break
            if not rec.get("_description") or not needs_review(rec, profile):
                continue
            rec["review_attempts"] = int(rec.get("review_attempts", 0)) + 1
            reviewed += 1
            try:
                res = classify.classify(_job_of(rec), profile, model=review_model, final_review=True,
                                        title_only=_title_only(rec))
            except Exception as e:
                print(f"AI review error on {rec['key']}: {e}", file=sys.stderr)
                errors += 1
                causes["review " + str(getattr(e, "category", type(e).__name__))] += 1
                continue
            finally:
                time.sleep(AI_GAP_SECONDS)
            rec.setdefault("ai_first", rec["ai"])  # keep the first-pass verdict, not an older review
            rec["review_version"] = REVIEW_VERSION
            rec["ai"] = res
            rec["ai_review_done"] = True
            rec["reviewed_by"] = ai.get("review_label", review_model)
            rec["verdict"] = verdict_of(res)
            rec["reason"] = res.get("reason", "")
    if errors:
        by_cause = ", ".join(f"{c} x{n}" for c, n in causes.most_common())
        log.append(f"AI classifier failed on {errors} posting(s) ({by_cause}); details are in the GitHub "
                   f"Actions log. Each posting is retried at most {MAX_AI_ATTEMPTS} times.")
    return used + reviewed


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated source ids")
    args = ap.parse_args(argv)
    only = {s for s in args.only.split(",") if s}

    sources = load_yaml("sources.yaml")
    profile = load_yaml("profile.yaml")
    rules = Rules(profile)
    DATA.mkdir(parents=True, exist_ok=True)
    saved = load_json(DATA / "jobs.json", {"jobs": {}})
    state = saved.get("jobs", {})
    skipped = saved.get("skipped", {})
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    tasks = [(school, src) for school in sources["schools"] for src in school["sources"]
             if not only or src["id"] in only]
    records, health, too_old = {}, [], {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for out, h, old in pool.map(lambda t: run_source(t[0], t[1], profile, rules, state, today, skipped), tasks):
            records.update(out)
            health.append(h)
            too_old.update(old)

    log = []
    ai_calls = apply_ai(records, profile, log)
    for rec in records.values():  # apply the current grouping rules to every saved AI result
        if rec.get("ai") and rec["ai"].get("verdict") in AI_TO_VERDICT and not rec.get("skip_ai"):
            rec["verdict"] = verdict_of(rec["ai"])

    # Keep jobs not seen today for a while (a search can miss a posting on one day),
    # but drop anything unseen for DROP_AFTER_DAYS. Sources that failed today get a longer grace period.
    failed = {h["source"] for h in health if h.get("status") not in ("ok",)}
    cutoff = (now - timedelta(days=DROP_AFTER_DAYS)).strftime("%Y-%m-%d")
    cutoff_failed = (now - timedelta(days=DROP_AFTER_DAYS_FAILED_SOURCE)).strftime("%Y-%m-%d")
    max_age = profile.get("max_posting_age_days")
    for key, old in state.items():
        if key in records or key in too_old:
            continue
        basis = age_basis(old.get("posted"), old.get("first_seen"), today)
        if not rules.title_ok(old.get("title", "")) or not is_recent(basis, today, max_age):
            continue  # no longer wanted (title rules changed) or posted too long ago
        limit = cutoff_failed if old.get("source") in failed else cutoff
        if old.get("last_seen", "") >= limit:
            records[key] = old
    by_source = {src["id"]: school for school in sources["schools"] for src in school["sources"]}
    for rec in records.values():
        rec.pop("_description", None)
        school = by_source.get(rec.get("source"))
        if school:  # keep rank and school name in step with sources.yaml (e.g. after re-ranking)
            rec["rank"], rec["school"] = school["rank"], school["name"]
        rec["active"] = rec.get("last_seen") == today

    meta = {"generated_utc": now.strftime("%Y-%m-%d %H:%M UTC"), "today": today,
            "ai_enabled": classify.available(), "ai_calls": ai_calls, "log": log,
            "total": len(records)}
    forget = (now - timedelta(days=FORGET_SKIPPED_AFTER_DAYS)).strftime("%Y-%m-%d")
    skipped_out = {k: v for k, v in skipped.items() if k not in records and v.get("seen", "") >= forget}
    skipped_out.update(too_old)
    with open(DATA / "jobs.json", "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "jobs": dict(sorted(records.items())),
                   "skipped": dict(sorted(skipped_out.items()))}, f, ensure_ascii=False, indent=1)
    with open(DATA / "health.json", "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "sources": sorted(health, key=lambda h: (h["rank"], h["source"]))},
                  f, ensure_ascii=False, indent=1)

    ok = sum(1 for h in health if h.get("status") == "ok")
    print(f"Sources ok: {ok}/{len(health)} | jobs stored: {len(records)} | AI calls: {ai_calls}")
    for line in log:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
