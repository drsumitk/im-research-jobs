import html
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup


def html_to_text(s):
    """Convert an HTML fragment to readable plain text."""
    if not s:
        return ""
    # Some sites double-escape entities (e.g. "&amp;#xa;"); unescape once before parsing.
    s = s.replace("&amp;#", "&#")
    soup = BeautifulSoup(s, "html.parser")
    for br in soup.find_all(["br", "p", "li", "div", "h1", "h2", "h3", "tr"]):
        br.append("\n")
    text = soup.get_text(" ")
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def iso_date(value):
    """Best-effort conversion of the date formats seen on careers sites to YYYY-MM-DD."""
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 1e12 else value
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    v = str(value).strip()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", v)
    if m:
        return m.group(1)
    for fmt in ("%b %d, %Y", "%m/%d/%Y", "%a %b %d %H:%M:%S UTC %Y", "%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return v  # leave unknown formats (e.g. "Posted 3 Days Ago") as text


_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_DATE_PATTERNS = [
    # 2026-10-21
    (re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)"), ("y", "m", "d")),
    # October 21, 2026 / Oct 21 2026 / December 22nd, 2025 / Sept. 4, 2026
    (re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b"), ("mon", "d", "y")),
    # 21 Oct 2026 / 4 September 2026
    (re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b"), ("d", "mon", "y")),
    # 10/21/2026, 10.21.2026, 10-21-2026 (US month-first)
    (re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b"), ("m", "d", "y")),
]


def find_date(text):
    """First calendar date found in free text, as YYYY-MM-DD; "" if none."""
    for pat, order in _DATE_PATTERNS:
        for m in pat.finditer(text or ""):
            parts = dict(zip(order, m.groups()))
            try:
                month = int(parts["m"]) if "m" in parts else _MONTHS.get(parts["mon"][:3].lower())
                if not month:
                    continue
                return datetime(int(parts["y"]), month, int(parts["d"])).strftime("%Y-%m-%d")
            except (ValueError, KeyError):
                continue
    return ""
