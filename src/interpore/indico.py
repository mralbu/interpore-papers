"""Parse an Indico event export into abstract records (2018 on).

Indico's ``contributionMetadata`` fossil gives, per contribution: ``friendly_id``
(the number shown on the site), ``title``, ``description`` (the abstract,
markdown with ``$...$`` math), ``type`` (presentation type), ``track`` (the
mini-symposium, e.g. "(MS10) Advances in imaging porous media"),
``primaryauthors`` / ``coauthors`` / ``speakers`` (name and affiliation; an
``emailHash`` is never kept) and ``folders`` (attachments: slides, posters).
"""

import re

from interpore import text

# "(MS10) Name", "MS 24 Name", "(MS06-A) Name", "MS1: Name", plain "Name".
_TRACK_RE = re.compile(r"^\(?\s*(MS)\s*(\d+)\s*(-\s*[A-Z])?\s*\)?\s*[:.\-–]?\s*(.*)$", re.S)


def parse_track(track: str | None) -> tuple[str | None, str | None]:
    """(code, name): ("MS10", "Advances in imaging ..."), or (None, name)."""
    track = text.clean_line(track)
    if not track:
        return None, None
    m = _TRACK_RE.match(track)
    if not m:
        return None, track
    code = f"MS{int(m.group(2)):02d}" + (m.group(3) or "").replace(" ", "")
    return code, m.group(4).strip() or None


def presentation_format(type_name: str | None, track_name: str | None) -> str:
    """Normalised presentation format: Invited, Oral, Poster, Online or Other."""
    t = (type_name or "").lower()
    tr = (track_name or "").lower()
    if re.search(r"invited|plenary|keynote", tr) or re.search(r"invited|plenary|keynote", t):
        return "Invited"
    if "online" in t:
        return "Online"
    if "poster" in t:
        return "Poster"
    if "oral" in t:
        return "Oral"
    return "Other"


def _person(p: dict) -> dict:
    name = text.clean_line(f"{p.get('first_name') or ''} {p.get('last_name') or ''}")
    if not name:
        name = text.clean_line(p.get("fullName"))
    return {"name": name, "affiliation": text.clean_line(p.get("affiliation")) or None}


def authors(c: dict) -> list[dict]:
    """Primary authors then co-authors, each person once (by name)."""
    out, seen = [], set()
    for p in (c.get("primaryauthors") or []) + (c.get("coauthors") or []):
        a = _person(p)
        key = a["name"].lower()
        if a["name"] and key not in seen:
            seen.add(key)
            out.append(a)
    return out


def attachments(c: dict) -> list[dict]:
    """Public attachments (slides, posters, videos): title and link, never the file."""
    out = []
    for folder in c.get("folders") or []:
        if folder.get("is_protected"):
            continue
        for a in folder.get("attachments") or []:
            if a.get("is_protected"):
                continue
            url = a.get("download_url") or a.get("link_url")
            if not url or not url.startswith("https://"):
                continue
            out.append({"title": text.clean_line(a.get("title") or a.get("filename")), "url": url})
    return out


def parse_event(export: dict, meeting: dict) -> list[dict]:
    event = export["results"][0]
    year = meeting["year"]
    records = []
    for c in event.get("contributions") or []:
        code, name = parse_track(c.get("track"))
        abstract = text.clean_abstract(c.get("description"))
        records.append(
            {
                "id": f"IP{year}-{c['friendly_id']}",
                "year": year,
                "meeting": meeting["number"],
                "source": "indico",
                "title": text.clean_line(c.get("title")),
                "authors": authors(c),
                "presenters": [_person(p)["name"] for p in c.get("speakers") or []],
                "abstract": abstract,
                "format": presentation_format(c.get("type"), name),
                "type": text.clean_line(c.get("type")) or None,
                "session_code": code,
                "session": name,
                "url": c.get("url"),
                "attachments": attachments(c),
            }
        )
    return records
