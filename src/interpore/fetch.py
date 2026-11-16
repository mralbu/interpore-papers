"""Stage: download the raw sources into ``data/raw/``.

- Indico (2018 on): the public JSON export of each annual meeting with every
  contribution (title, abstract, authors and affiliations, mini-symposium,
  presentation type, attachments): ``/export/event/<id>.json?detail=contributions``.
  One request per meeting, saved as ``data/raw/indico/<id>.json``.
- Books of abstracts (2016, 2017, which predate Indico): the PDFs linked from
  interpore.org, saved as ``data/raw/books/<year>.pdf``.

Meetings and their sources come from ``meetings.yaml``. Files already on disk
are kept unless ``force`` (or ``--refresh`` for Indico exports, which change
while a meeting's programme is still being built).
"""

import json
import time
import urllib.request
from pathlib import Path

from interpore import cache, meetings, paths

# A generic client name: no personal contact details in requests.
USER_AGENT = "interpore-papers/0.1 (abstracts explorer; python-urllib)"
TIMEOUT = 300


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read()
        except OSError:
            if attempt == 3:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def indico_url(event: int) -> str:
    return f"{paths.INDICO_BASE}/export/event/{event}.json?detail=contributions"


def indico_path(event: int) -> Path:
    return paths.INDICO_DIR / f"{event}.json"


def book_path(year: int) -> Path:
    return paths.BOOKS_DIR / f"{year}.pdf"


def book_years() -> list[int]:
    """Meetings whose abstracts come from the book (a book and no Indico event)."""
    return [m["year"] for m in meetings.meetings() if m.get("book") and not m.get("indico")]


def run(force: bool = False, refresh: bool = False) -> list[str]:
    log = []
    for m in meetings.meetings():
        if m.get("upcoming"):
            continue
        if ev := m.get("indico"):
            out = indico_path(ev)
            if out.exists() and not (force or refresh):
                log.append(f"{m['year']}: indico {ev} cached")
                continue
            data = json.loads(_get(indico_url(ev)))
            results = data.get("results") or []
            if not results:
                raise SystemExit(f"Indico event {ev} returned no results (is it public?)")
            cache.write_json_atomic(out, data)
            n = len(results[0].get("contributions") or [])
            log.append(f"{m['year']}: indico {ev} -> {n} contributions")
        elif m["year"] in book_years():
            out = book_path(m["year"])
            if out.exists() and not force:
                log.append(f"{m['year']}: book cached")
                continue
            body = _get(m["book"])
            if not body.startswith(b"%PDF"):
                raise SystemExit(f"{m['book']} is not a PDF")
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(".tmp")
            tmp.write_bytes(body)
            tmp.replace(out)
            log.append(f"{m['year']}: book -> {len(body) / 1e6:.1f} MB")
    return log
