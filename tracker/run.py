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
            known = (skipped.get(job.key) or {}).get("posted") or (old or {}).get("posted")
            if known and not is_recent(known, today, max_age):
                too_old[job.key] = {"posted": known, "seen": today}
                late_old += 1
                continue  # an exact date read earlier shows it is too old
            ai_pending = bool(old) and classify.available() and not old.get("ai") \
                and int(old.get("ai_attempts", 0)) < MAX_AI_ATTEMPTS
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
            if not is_recent(job.posted, today, max_age):
                too_old[job.key] = {"posted": job.posted, "seen": today}
                late_old += 1
                continue  # the detail page gave an exact date outside the window
            ev = rules.evaluate(job)
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
                "verdict": ev["verdict"], "reason": ev["reason"],
                "_description": job.description,  # removed before saving
            }
        health.update(status="ok", new_details=new_details, detail_errors=detail_errors,
                      candidates=len(cands) - late_old, too_old=len(titled) - len(cands) + late_old)
    except RobotsBlocked as e:
        health.update(status="blocked", error=str(e)[:300])
    except Exception as e:
        health.update(status="error", error=f"{type(e).__name__}: {str(e)[:300]}")
        traceback.print_exc()
    return out, health, too_old


AI_TO_VERDICT = {"match": "Match", "check": "Check", "other_dept": "Other dept", "excluded": "Excluded"}


def apply_ai(records, profile, log):
    if not classify.available():
        log.append("AI classifier off (no ANTHROPIC_API_KEY secret).")
        return 0
    budget = int(profile.get("ai", {}).get("max_calls_per_run", 150))
    used = errors = 0
    causes = Counter()
    from .models import Job
    for rec in records.values():
        if used >= budget:
            log.append(f"AI budget of {budget} calls reached; remaining jobs are classified on the next run.")
            break
        if rec.get("ai") or not rec.get("_description") or int(rec.get("ai_attempts", 0)) >= MAX_AI_ATTEMPTS:
            continue
        job = Job(rec["source"], rec["key"], rec["title"], rec["url"], rec["location"],
                  rec["department"], rec["posted"], rec["_description"])
        rec["ai_attempts"] = int(rec.get("ai_attempts", 0)) + 1
        used += 1
        try:
            res = classify.classify(job, profile)
        except Exception as e:
            # Full detail goes to the private Actions log; the public page gets only the cause category.
            print(f"AI error on {rec['key']}: {e}", file=sys.stderr)
            errors += 1
            causes[getattr(e, "category", type(e).__name__)] += 1
            continue
        finally:
            time.sleep(AI_GAP_SECONDS)
        rec["ai"] = res
        rec["verdict"] = AI_TO_VERDICT[res["verdict"]]
        rec["reason"] = res.get("reason", "")
    if errors:
        by_cause = ", ".join(f"{c} x{n}" for c, n in causes.most_common())
        log.append(f"AI classifier failed on {errors} posting(s) ({by_cause}); details are in the GitHub "
                   f"Actions log. Each posting is retried at most {MAX_AI_ATTEMPTS} times.")
    return used


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
    with ThreadPoolExecutor(max_workers=6) as pool:
        for out, h, old in pool.map(lambda t: run_source(t[0], t[1], profile, rules, state, today, skipped), tasks):
            records.update(out)
            health.append(h)
            too_old.update(old)

    log = []
    ai_calls = apply_ai(records, profile, log)

    # Keep jobs not seen today for a while (a search can miss a posting on one day),
    # but drop anything unseen for DROP_AFTER_DAYS. Sources that failed today get a longer grace period.
    failed = {h["source"] for h in health if h.get("status") not in ("ok",)}
    cutoff = (now - timedelta(days=DROP_AFTER_DAYS)).strftime("%Y-%m-%d")
    cutoff_failed = (now - timedelta(days=DROP_AFTER_DAYS_FAILED_SOURCE)).strftime("%Y-%m-%d")
    max_age = profile.get("max_posting_age_days")
    for key, old in state.items():
        if key in records or key in too_old:
            continue
        if not rules.title_ok(old.get("title", "")) or not is_recent(old.get("posted"), today, max_age):
            continue  # no longer wanted (title rules changed) or posted too long ago
        limit = cutoff_failed if old.get("source") in failed else cutoff
        if old.get("last_seen", "") >= limit:
            records[key] = old
    for rec in records.values():
        rec.pop("_description", None)
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
