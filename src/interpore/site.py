"""Stage: export the published site data (``site/data/``).

- ``papers.json``: one entry per abstract without the abstract text (title,
  authors with affiliations, year, format, mini-symposium, links, topic, map
  position, similar abstracts). Loaded first, so the list and map show fast.
- ``abstracts.json``: ``{id: abstract}``, loaded in the background (search
  over abstracts and the reading pane use it). Set ``INCLUDE_ABSTRACTS = False``
  to publish without abstracts.
- ``topics.json``: topics with display names.
- ``history.json`` and ``charts/*.json``: the History view (``history.py``).
- ``llms.txt`` files (``llms.py``).

Abstracts belong to their authors; the site links each one to its page on
events.interpore.org (or its page in the book of abstracts). Emails, email
hashes and attachment files are never published (attachments are links).
"""

import json

import numpy as np

from interpore import cache, embed, history, llms, paths, records, topics

INCLUDE_ABSTRACTS = True
PAPERS_JSON = paths.SITE_DATA_DIR / "papers.json"
ABSTRACTS_JSON = paths.SITE_DATA_DIR / "abstracts.json"
TOPICS_JSON = paths.SITE_DATA_DIR / "topics.json"
MAX_FILE_BYTES = 100 * 10**6  # GitHub Pages per-file limit
N_SIMILAR = 8


def similar(model: str, k: int = N_SIMILAR) -> dict[str, list[str]]:
    """The k nearest abstracts to each one by cosine similarity (rows are L2-normalised)."""
    ids, vectors = embed.load(model)
    out = {}
    for start in range(0, len(ids), 2048):
        sims = vectors[start : start + 2048] @ vectors.T
        for row in range(sims.shape[0]):
            sims[row, start + row] = -np.inf
        top = np.argpartition(-sims, k, axis=1)[:, :k]
        for row, cols in enumerate(top):
            cols = cols[np.argsort(-sims[row, cols])]
            out[ids[start + row]] = [ids[j] for j in cols]
    return out


def topic_labels(topic_data: dict) -> list[dict]:
    """Topics with display names. ``topics.yaml`` rename values are either a name
    or ``{name, short}`` (``short`` is the map label); the c-TF-IDF label stays in
    ``keyword_label``."""
    import yaml

    raw = {}
    if paths.TOPICS_YAML.exists():
        raw = (yaml.safe_load(paths.TOPICS_YAML.read_text(encoding="utf-8")) or {}).get(
            "rename"
        ) or {}
    out = []
    for t in topic_data["topics"]:
        t = {**t, "keyword_label": " / ".join(t["keywords"][:3])}
        r = raw.get(t["id"])
        if isinstance(r, dict):
            t["label"], t["short"] = r["name"], r.get("short") or r["name"]
        elif isinstance(r, str):
            t["label"] = t["short"] = r
        out.append(t)
    return out


def build() -> tuple[list[dict], dict[str, str], list[dict]]:
    recs = records.load()
    topic_data = json.loads(topics.OUTPUT.read_text(encoding="utf-8"))
    neighbours = similar(topic_data["model"])
    papers, abstracts = [], {}
    for r in recs:
        pos = topic_data["papers"].get(r["id"])
        if not pos:
            continue
        paper = {
            "id": r["id"],
            "year": r["year"],
            "title": r["title"],
            "authors": [a["name"] for a in r["authors"]],
            "affs": [a["affiliation"] for a in r["authors"]],
            "presenters": r["presenters"],
            "format": r["format"],
            "session_code": r["session_code"],
            "session": r["session"],
            "source": r["source"],
            "url": r["url"],
            "topic": pos["topic"],
            "outlier": pos["outlier"],
            "x": pos["x"],
            "y": pos["y"],
            "similar": neighbours.get(r["id"], []),
        }
        if r["attachments"]:
            paper["attachments"] = r["attachments"]
        papers.append({k: v for k, v in paper.items() if v not in (None, [], "")})
        if INCLUDE_ABSTRACTS:
            abstracts[r["id"]] = r["abstract"]
    return papers, abstracts, topic_labels(topic_data)


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"


def run() -> str:
    papers, abstracts, topic_list = build()
    cache.write_text_atomic(PAPERS_JSON, _dump(papers))
    cache.write_text_atomic(ABSTRACTS_JSON, _dump(abstracts))
    cache.write_json_atomic(TOPICS_JSON, topic_list)
    hist_files = history.write(records.load(), papers, topic_list)
    llms_files = llms.write(papers, abstracts, topic_list)
    files = [PAPERS_JSON, ABSTRACTS_JSON, TOPICS_JSON, *hist_files, *llms_files]
    sizes = {p: p.stat().st_size for p in files}
    too_big = [p.name for p, s in sizes.items() if s > MAX_FILE_BYTES]
    if too_big:
        raise SystemExit(f"over the 100 MB GitHub Pages file limit: {too_big}")
    total = sum(f.stat().st_size for f in paths.SITE_DIR.rglob("*") if f.is_file())
    return (
        f"{len(papers)} abstracts, {len(topic_list)} topics -> "
        f"{PAPERS_JSON.relative_to(paths.ROOT)} ({sizes[PAPERS_JSON] / 1e6:.1f} MB), "
        f"abstracts.json ({sizes[ABSTRACTS_JSON] / 1e6:.1f} MB), "
        f"{len(hist_files)} history files, {len(llms_files)} llms files, "
        f"site total {total / 1e6:.1f} MB\n"
    )
