"""llms.txt files for the published site (https://llmstxt.org/ convention).

Written by ``site.run()`` from the same data as ``papers.json``/``abstracts.json``,
so they hold only what the site already publishes:

- ``site/llms.txt``: short index (what the corpus is, caveats, one link per topic).
- ``site/llms/<topic>.txt``: per topic, every abstract (newest meeting first)
  with authors, mini-symposium and its link.
- ``site/llms-full.txt``: the whole catalogue, one line per abstract (no
  abstract text), grouped by topic.

Markdown in ``.txt`` files: browsers display them, and the Pages guard keeps
refusing ``.md`` under ``site/``.
"""

import re

from interpore import cache, paths

SITE_URL = "https://mralbu.github.io/interpore-papers/"
LLMS_TXT = paths.SITE_DIR / "llms.txt"
LLMS_FULL = paths.SITE_DIR / "llms-full.txt"
TOPIC_DIR = paths.SITE_DIR / "llms"


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "topic"


def one_line(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def link_text(s: str) -> str:
    """Escape what would break a markdown link label."""
    return one_line(s).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def topic_files(topic_list: list[dict]) -> dict[int, str]:
    names, seen = {}, set()
    for t in sorted(topic_list, key=lambda t: t["id"]):
        name = slug(t["label"])
        if name in seen:
            name = f"{name}-{t['id']}"
        seen.add(name)
        names[t["id"]] = f"{name}.txt"
    return names


def by_topic(papers: list[dict], topic_list: list[dict]) -> list[tuple[dict, list[dict]]]:
    groups = {t["id"]: [] for t in topic_list}
    for p in papers:
        groups[p["topic"]].append(p)
    order = sorted(topic_list, key=lambda t: (-len(groups[t["id"]]), t["id"]))
    return [(t, sorted(groups[t["id"]], key=lambda p: (-p["year"], p["id"]))) for t in order]


def _session(p: dict) -> str:
    code, name = p.get("session_code"), p.get("session")
    if code and name and code not in name:
        return f"{code} {name}"
    return name or code or ""


def index(papers: list[dict], groups, files: dict[int, str]) -> str:
    years = sorted({p["year"] for p in papers})
    lines = [
        "# InterPore Abstracts Explorer",
        "",
        f"> An explorer for {len(papers):,} abstracts of the annual meetings of the "
        f"International Society for Porous Media (InterPore), {years[0]}–{years[-1]}: flow, "
        "transport and mechanics in natural and industrial porous media, grouped by topic. "
        "InterPore publishes abstracts, not full papers; each entry links to its page on "
        "events.interpore.org (2018 on) or its page in the book of abstracts (2016, 2017).",
        "",
        "- Abstracts are the authors' own text as submitted; this site adds topics, a map "
        "and similar-abstract links (from text embeddings), nothing written by an AI.",
        "- No abstracts are online for the 2009–2015 meetings; they appear only in the "
        "History view.",
        f"- Each abstract has a page at `{SITE_URL}#<ID>` (e.g. `#IP2024-164`).",
        "",
        "## Topics",
        "",
    ]
    for t, ps in groups:
        lines.append(
            f"- [{link_text(t['label'])}]({SITE_URL}llms/{files[t['id']]}): {len(ps)} "
            f"abstracts. Keywords: {', '.join(t['keywords'][:6])}"
        )
    lines += [
        "",
        "## Data",
        "",
        f"- [All abstracts, one line each]({SITE_URL}llms-full.txt): ID, year, title, "
        "authors and mini-symposium, grouped by topic",
        f"- [papers.json]({SITE_URL}data/papers.json): metadata, map coordinates, topics "
        "and similar-abstract links",
        f"- [abstracts.json]({SITE_URL}data/abstracts.json): abstract text by ID",
        f"- [history.json]({SITE_URL}data/history.json): every meeting since 2009 with "
        "place, dates and per-meeting statistics",
        "",
        "## Optional",
        "",
        "- [InterPore](https://www.interpore.org/): the society",
        "- [events.interpore.org](https://events.interpore.org/): the conference system",
        "",
    ]
    return "\n".join(lines)


def topic_page(t: dict, ps: list[dict], abstracts: dict[str, str]) -> str:
    lines = [
        f"# {one_line(t['label'])}",
        "",
        f"> {len(ps)} InterPore abstracts in this topic, newest meeting first. Topic "
        f"keywords: {', '.join(t['keywords'])}.",
        "",
        f"Index of all topics: {SITE_URL}llms.txt",
        "",
    ]
    for p in ps:
        lines += [f"## {one_line(p['title'])}", ""]
        lines.append(f"- ID: {p['id']}, InterPore{p['year']}, {p['format']}")
        if p.get("authors"):
            lines.append(f"- Authors: {', '.join(p['authors'])}")
        if s := _session(p):
            lines.append(f"- Session: {s}")
        lines.append(f"- [Source]({p['url']}) · [On the site]({SITE_URL}#{p['id']})")
        lines.append("")
        if a := abstracts.get(p["id"]):
            lines += [one_line(a), ""]
    return "\n".join(lines)


def full_line(p: dict) -> str:
    parts = [f"- [{link_text(p['title'])}]({p['url']}) — {p['id']}, {p['year']}."]
    if p.get("authors"):
        parts.append(f"{', '.join(p['authors'])}.")
    if s := _session(p):
        parts.append(f"Session: {one_line(s)}.")
    return " ".join(parts)


def full(papers: list[dict], groups) -> str:
    lines = [
        "# InterPore Abstracts Explorer: all abstracts",
        "",
        f"> All {len(papers):,} abstracts, one line each: title (linked to the source), ID, "
        "year, authors and mini-symposium. Grouped by topic (largest first), newest first.",
        "",
        f"Per-topic files with the abstracts: {SITE_URL}llms.txt",
        "",
    ]
    for t, ps in groups:
        lines += [f"## {one_line(t['label'])}", "", *map(full_line, ps), ""]
    return "\n".join(lines)


def write(papers: list[dict], abstracts: dict[str, str], topic_list: list[dict]) -> list:
    """Write every llms file (replacing stale topic files); returns their paths."""
    files = topic_files(topic_list)
    groups = by_topic(papers, topic_list)
    TOPIC_DIR.mkdir(parents=True, exist_ok=True)
    for old in TOPIC_DIR.iterdir():
        if old.name not in files.values():
            old.unlink()
    out = []
    for t, ps in groups:
        path = TOPIC_DIR / files[t["id"]]
        cache.write_text_atomic(path, topic_page(t, ps, abstracts))
        out.append(path)
    cache.write_text_atomic(LLMS_TXT, index(papers, groups, files))
    cache.write_text_atomic(LLMS_FULL, full(papers, groups))
    return [LLMS_TXT, LLMS_FULL, *out]
