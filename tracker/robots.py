"""Minimal robots.txt reader following RFC 9309: the longest matching rule wins, Allow wins ties,
'*' and '$' wildcards are supported. (Python's urllib.robotparser uses first-match order instead,
which wrongly blocks sites such as hiring.jhu.edu that list "Disallow: /" before specific Allows.)"""
import re


def _to_regex(path):
    rx = re.escape(path).replace(r"\*", ".*")
    if rx.endswith(r"\$"):
        rx = rx[:-2] + "$"
    return re.compile(rx)


class Robots:
    def __init__(self, text, agent_token="imresearchjobtracker"):
        self.rules = []          # (length, allow, regex)
        self.crawl_delay = None
        groups, current, agents, seen_rule = [], None, [], False
        for raw in (text or "").lstrip("﻿").splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, val = (x.strip() for x in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if current is None or seen_rule:
                    current = {"agents": [], "rules": [], "delay": None}
                    groups.append(current)
                    seen_rule = False
                current["agents"].append(val.lower())
            elif current is not None and key in ("allow", "disallow"):
                seen_rule = True
                if val:
                    current["rules"].append((len(val), key == "allow", _to_regex(val)))
            elif current is not None and key == "crawl-delay":
                seen_rule = True
                try:
                    current["delay"] = float(val)
                except ValueError:
                    pass
        specific = [g for g in groups if any(agent_token in a for a in g["agents"])]
        chosen = specific or [g for g in groups if "*" in g["agents"]]
        for g in chosen:
            self.rules.extend(g["rules"])
            if g["delay"] is not None:
                self.crawl_delay = g["delay"]

    def allowed(self, path_and_query):
        best = None
        for length, allow, rx in self.rules:
            if rx.match(path_and_query):
                if best is None or length > best[0] or (length == best[0] and allow):
                    best = (length, allow)
        return True if best is None else best[1]
