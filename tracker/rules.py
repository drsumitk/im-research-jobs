"""Keyword rules: title gate, Internal Medicine division, wet-lab vs clinical signals, eligibility flags.
These run on every job and are the fallback when no AI key is configured."""
import re


def _rx(patterns):
    return [re.compile(p, re.I) for p in patterns]


class Rules:
    def __init__(self, profile):
        self.inc = _rx(profile["title_include"])
        self.exc = _rx(profile["title_exclude"])
        self.divs = {name: _rx(pats) for name, pats in profile["im_divisions"].items()}
        self.non_im = _rx(profile["non_im_departments"])
        self.wet = _rx(profile["wet_lab_terms"])
        self.wet_neg = _rx(profile["wet_lab_negations"])
        self.dry = _rx(profile["dry_terms"])
        self.flags = {k: _rx(v) for k, v in profile["flags"].items()}

    def title_ok(self, title):
        t = title or ""
        return any(p.search(t) for p in self.inc) and not any(p.search(t) for p in self.exc)

    def division(self, department, title, description):
        """Department/title text decides first; the description is only a weaker hint."""
        stated = re.search(r"Department\s*:\s*([^\n]{3,140})", description or "")
        strong = f"{department} {title} {stated.group(1) if stated else ''}"
        # A non-IM department name wins first: "Pediatrics-Rheumatology" is pediatrics, not IM.
        if any(p.search(strong) for p in self.non_im):
            return "Not Internal Medicine", "department"
        for name, pats in self.divs.items():
            if any(p.search(strong) for p in pats):
                if name.startswith("Department of Medicine"):
                    break  # look for a more specific division in the description
                return name, "department"
        head = (description or "")[:1500]
        for name, pats in self.divs.items():
            if any(p.search(head) for p in pats):
                return name, "description"
        if any(p.search(head) for p in self.non_im):
            return "Not Internal Medicine", "description"
        if any(p.search(strong) for p in self.divs["Department of Medicine (division not stated)"]):
            return "Department of Medicine (division not stated)", "department"
        return "Unclear", "none"

    def research_type(self, description):
        text = description or ""
        negated = any(p.search(text) for p in self.wet_neg)
        wet_hits = sorted({m.group(0).lower() for p in self.wet for m in p.finditer(text)})
        dry_hits = sorted({m.group(0).lower() for p in self.dry for m in p.finditer(text)})
        if negated:
            wet_hits = []
        if wet_hits and len(wet_hits) >= 2 and len(wet_hits) >= len(dry_hits) / 2:
            kind = "Wet lab"
        elif wet_hits and dry_hits:
            kind = "Mixed or unclear"
        elif dry_hits:
            kind = "Clinical or dry research"
        elif wet_hits:
            kind = "Mixed or unclear"
        else:
            kind = "Unclear"
        return kind, wet_hits[:8], dry_hits[:8]

    def eligibility(self, description):
        text = description or ""
        out = {k: any(p.search(text) for p in pats) for k, pats in self.flags.items()}
        notes = []
        if out["citizenship_required"]:
            notes.append("US citizenship or permanent residency mentioned")
        if out["no_sponsorship"]:
            notes.append("States no visa sponsorship")
        if out["phd_only"] and not out["md_or_foreign_md_ok"]:
            notes.append("PhD appears required with no MD alternative")
        if out["sponsorship_mentioned"]:
            notes.append("Visa sponsorship mentioned")
        return out, notes

    def evaluate(self, job):
        div, div_src = self.division(job.department, job.title, job.description)
        kind, wet, dry = self.research_type(job.description)
        flags, notes = self.eligibility(job.description)
        blocking = flags["citizenship_required"] or flags["no_sponsorship"] or (
            flags["phd_only"] and not flags["md_or_foreign_md_ok"])
        if not job.description:
            verdict, reason = "Check", "Description could not be read; open the posting."
        elif kind == "Wet lab":
            verdict, reason = "Excluded", "Wet-lab signals: " + ", ".join(wet[:4])
        elif blocking:
            verdict, reason = "Excluded", "; ".join(n for n in notes if n != "Visa sponsorship mentioned")
        elif div == "Not Internal Medicine":
            verdict, reason = "Other dept", "Department does not look like Internal Medicine"
        elif kind == "Clinical or dry research" and div != "Unclear" and div_src == "department":
            verdict, reason = "Match", f"{kind}; {div}"
        elif kind == "Clinical or dry research" and div != "Unclear":
            verdict, reason = "Check", f"{kind}; division guessed from the description: {div}"
        else:
            verdict, reason = "Check", f"{kind}; division: {div}"
        return {
            "division": div, "division_source": div_src, "research_type": kind,
            "wet_terms": wet, "dry_terms": dry, "flags": flags, "notes": notes,
            "verdict": verdict, "reason": reason,
        }
