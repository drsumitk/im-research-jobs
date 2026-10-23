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
