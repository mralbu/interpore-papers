"""Stage: one normalised record per abstract -> ``data/records.json``.

Sources: Indico exports (2018 on) and the 2016/2017 books of abstracts (see
``indico.py`` and ``books.py``). Kept: contributions with an abstract of at
least ``MIN_WORDS`` words (drops placeholders, award ceremonies and the
like). Within a meeting, a second contribution with the same title and first
author is a duplicate submission and is dropped. A per-year report of what
was kept goes to ``data/records-report.txt``.

Record fields: id (``IP<year>-<n>``), year, meeting (ordinal), source
(indico | book), title, authors [{name, affiliation}], presenters, abstract,
format (Invited | Oral | Poster | Online | Other), type (Indico's own label),
session_code (e.g. MS10), session (mini-symposium name), url (the abstract
on Indico, or the book page), attachments [{title, url}].
"""

import json
import re
from collections import Counter

from interpore import books, cache, fetch, indico, meetings, paths, text

MIN_WORDS = 25


def _dedup_key(r: dict) -> tuple:
    title = re.sub(r"\W+", " ", r["title"].lower()).strip()
    first = text.name_key(r["authors"][0]["name"]) if r["authors"] else ""
    return (r["year"], title, first)


def load_year(m: dict) -> list[dict]:
    if ev := m.get("indico"):
        path = fetch.indico_path(ev)
        if not path.exists():
            return []
        return indico.parse_event(json.loads(path.read_text(encoding="utf-8")), m)
    if m["year"] in books.PARSERS:
        path = fetch.book_path(m["year"])
        if not path.exists():
            return []
        return books.PARSERS[m["year"]](books.page_texts(path), m, m["book"])
    return []


def run() -> tuple[list[dict], str]:
    kept, report = [], []
    report.append(f"{'year':>4} {'raw':>5} {'short':>5} {'dupes':>5} {'kept':>5}  formats")
    for m in meetings.meetings():
        raw = load_year(m)
        if not raw:
            continue
        seen, n_short, n_dup, year_kept = set(), 0, 0, []
        # Contributions with a session first, so a duplicate keeps the scheduled copy.
        for r in sorted(raw, key=lambda r: (r["session"] is None, r["id"])):
            if text.word_count(r["abstract"]) < MIN_WORDS or not r["title"]:
                n_short += 1
                continue
            key = _dedup_key(r)
            if key in seen:
                n_dup += 1
                continue
            seen.add(key)
            year_kept.append(r)
        ids = Counter(r["id"] for r in year_kept)
        clash = [i for i, n in ids.items() if n > 1]
        if clash:
            raise SystemExit(f"duplicate ids in {m['year']}: {clash[:5]}")
        fmt = Counter(r["format"] for r in year_kept)
        report.append(
            f"{m['year']:>4} {len(raw):>5} {n_short:>5} {n_dup:>5} {len(year_kept):>5}  "
            + ", ".join(f"{k} {v}" for k, v in fmt.most_common())
        )
        kept.extend(sorted(year_kept, key=lambda r: r["id"]))
    report.append(f"total {len(kept)}")
    no_auth = sum(not r["authors"] for r in kept)
    no_sess = sum(not r["session"] for r in kept)
    report.append(f"without authors: {no_auth}, without session: {no_sess}")
    cache.write_json_atomic(paths.RECORDS, kept)
    out = "\n".join(report) + "\n"
    cache.write_text_atomic(paths.RECORDS_REPORT, out)
    return kept, out


def load() -> list[dict]:
    return json.loads(paths.RECORDS.read_text(encoding="utf-8"))
