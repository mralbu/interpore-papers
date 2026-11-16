"""Parse the 2016 and 2017 books of abstracts (before Indico) into records.

Both books have one abstract per page start; long abstracts continue on the
next page(s), which have no header and are appended to the abstract before.

- 2016 (LaTeX, Cincinnati): page header "8th International Conference on
  Porous Media & Annual Meeting", then title, "Presenter:", "Contact Author:",
  "AUTHORS" (names with affiliation numbers, then numbered affiliations),
  "ABSTRACT", optional "REFERENCES" (dropped), printed page number last. The
  minisymposium of each abstract comes from the table of contents, which
  lists each section's abstracts by printed page. IDs are ``IP2016-<page>``.
- 2017 (Rotterdam): header lines "<session>", "9th International Conference
  ... Rotterdam", "2017, Submission <n>", then title, one line per author
  ("Name, affiliation, country, email"; emails are never kept), abstract.
  IDs are ``IP2017-<submission>``.

Text comes from pypdfium2 (no poppler needed). Paragraph breaks are guessed
from short lines ending a sentence.
"""

import re
from pathlib import Path

from interpore import text

EMAIL_RE = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")


def page_texts(pdf_path: Path) -> list[str]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        out = []
        for i in range(len(pdf)):
            tp = pdf[i].get_textpage()
            out.append(tp.get_text_range().replace("\r\n", "\n").replace("\r", "\n"))
        return out
    finally:
        pdf.close()


def join_lines(lines: list[str]) -> str:
    """Hard-wrapped lines -> paragraphs. A line that ends a sentence and is
    clearly shorter than the full lines ends a paragraph; hyphenated line
    breaks are joined."""
    lines = [ln.rstrip() for ln in lines]
    lines = [ln for ln in lines if ln.strip()]
    if not lines:
        return ""
    full = sorted(len(ln) for ln in lines)[int(len(lines) * 0.8)]
    paras: list[list[str]] = [[]]
    for ln in lines:
        paras[-1].append(ln.strip())
        if ln.endswith((".", ":", "!", "?")) and len(ln) < 0.8 * full:
            paras.append([])
    out = []
    for p in paras:
        s = ""
        for ln in p:
            if s.endswith("-") and not s.endswith(" -") and ln[:1].islower():
                s = s[:-1] + ln
            elif s.endswith("￾"):  # pdfium's mark for a soft line-break hyphen
                s = s[:-1] + ln
            else:
                s = f"{s} {ln}" if s else ln
        if s:
            out.append(s)
    return text.clean_abstract("\n\n".join(out))


# --- 2016 ----------------------------------------------------------------------

H2016 = "8th International Conference on Porous Media & Annual Meeting"
_TOC_HEAD_RE = re.compile(
    r"^((?:Minisymposium|General Session)\s+[\d.]+|Special Session)\s*[-–]\s*(.+)$"
)
# Headings without a number: (code, name).
_TOC_PLAIN = {
    "Plenary speakers": ("Plenary", "Plenary speakers"),
    "Invited speakers": ("Invited", "Invited speakers"),
}
_PAGE_RE = re.compile(r"(?:^|\s)(\d{1,3})$")


def toc_2016(pages: list[str]) -> dict[int, tuple[str, str]]:
    """Printed page -> (session code, session name), from the table of contents."""
    out: dict[int, tuple[str, str]] = {}
    current = None
    for t in pages[:60]:
        if not re.search(r"Minisymposium|General Session|Special Session|Plenary speakers", t):
            continue
        lines = [ln.strip() for ln in t.split("\n") if ln.strip()]
        i = 0
        while i < len(lines):
            ln = lines[i]
            m = _TOC_HEAD_RE.match(ln)
            if ln in _TOC_PLAIN:
                current = _TOC_PLAIN[ln]
            elif m:
                name = m.group(2)
                # A long heading wraps; its continuation starts lower case.
                if i + 1 < len(lines) and lines[i + 1][:1].islower() and len(ln) > 55:
                    name = f"{name} {lines[i + 1]}"
                    i += 1
                code = (
                    m.group(1)
                    .replace("Minisymposium", "MS")
                    .replace("General Session", "GS")
                    .replace("Special Session", "SS")
                )
                current = (code, text.clean_line(name))
            elif current:
                pm = _PAGE_RE.search(ln)
                if pm and not _TOC_HEAD_RE.match(ln):
                    out.setdefault(int(pm.group(1)), current)
            i += 1
    return out


_POSITION_RE = re.compile(
    r"(?i)\b(student|professor|prof\.?|researcher|fellow|engineer|scientist|manager|lecturer|"
    r"director|candidate|post-?doc\w*|assistant|associate|head|chair|ph\.?d|msc|master|"
    r"graduate|undergraduate|staff|technician|consultant|leader|president|ceo|cto|founder|"
    r"specialist|advisor|analyst|intern|reader|dean|member)\b"
)


def _authors_2016(block: list[str]) -> list[dict]:
    """'Name 1, Name 2,3' lines, then '1 Position, Organisation, ..., CC' lines."""
    names_txt, affs, cur = [], {}, None
    for ln in block:
        m = re.match(r"^(\d{1,2})\s+(\S.*)$", ln)
        if m and (affs or names_txt):
            cur = int(m.group(1))
            affs[cur] = m.group(2)
        elif cur is not None:
            affs[cur] += " " + ln
        else:
            names_txt.append(ln)
    names = []
    for piece in re.split(r"(?<=\d)\s*,\s*(?=\D)|,\s+(?=[^\d\s])", " ".join(names_txt)):
        m = re.match(r"^(.*?)\s*((?:\d+\s*,?\s*)*)$", piece.strip())
        if not m or not m.group(1).strip():
            continue
        nums = [int(n) for n in re.findall(r"\d+", m.group(2))]
        names.append((text.clean_line(m.group(1)), nums))

    def org(a: str) -> str:
        parts = [p.strip() for p in a.split(",") if p.strip()]
        # Form fields: [position,] organisation, address..., postcode, city, country code.
        if len(parts) >= 3:
            i = 1 if _POSITION_RE.search(parts[0]) else 0
            return text.clean_line(f"{parts[i]}, {parts[-1]}")
        return text.clean_line(a)

    return [
        {"name": n, "affiliation": "; ".join(org(affs[k]) for k in nums if k in affs) or None}
        for n, nums in names
    ]


def parse_2016(pages: list[str], meeting: dict, pdf_url: str) -> list[dict]:
    toc = toc_2016(pages)
    starts = [i for i, t in enumerate(pages) if "\nPresenter:" in t and t.startswith(H2016)]
    records = []
    for k, i in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(pages)
        lines: list[str] = []
        for j in range(i, end):
            pl = pages[j].split("\n")
            if pl and pl[0].startswith(H2016):
                pl = pl[1:]
            while pl and not pl[-1].strip():
                pl.pop()
            if pl and re.fullmatch(r"\d{1,3}", pl[-1].strip()):
                if j == i:
                    printed = int(pl[-1].strip())
                pl = pl[:-1]
            lines.extend(pl)
        if not lines:
            continue
        idx = {ln.strip(): n for n, ln in reversed(list(enumerate(lines)))}
        p_at = next(n for n, ln in enumerate(lines) if ln.startswith("Presenter:"))
        title = text.clean_line(" ".join(lines[:p_at]))
        presenter = text.clean_line(lines[p_at].split(":", 1)[1])
        a_at, ab_at = idx.get("AUTHORS"), idx.get("ABSTRACT")
        if ab_at is None:
            continue
        block = [ln.strip() for ln in lines[(a_at or p_at) + 1 : ab_at] if ln.strip()]
        if a_at is None:
            block = [ln for ln in block if not ln.startswith("Contact Author:")]
        body = lines[ab_at + 1 :]
        ref = next((n for n, ln in enumerate(body) if ln.strip() == "REFERENCES"), None)
        if ref is not None:
            body = body[:ref]
        code, name = toc.get(printed, (None, None))
        records.append(
            {
                "id": f"IP2016-{printed}",
                "year": 2016,
                "meeting": meeting["number"],
                "source": "book",
                "title": title,
                "authors": _authors_2016(block),
                "presenters": [presenter] if presenter else [],
                "abstract": join_lines(body),
                "format": "Other",
                "type": None,
                "session_code": code,
                "session": name,
                "url": f"{pdf_url}#page={i + 1}",
                "attachments": [],
            }
        )
    return records


# --- 2017 ----------------------------------------------------------------------

_SUB_RE = re.compile(r"^2017, Submission (\d+)\s*$")
_AUTHOR_START_RE = re.compile(r"^([^,@:;]{2,60}),\s")


def _is_author_start(line: str) -> bool:
    """'Given Surname, affiliation...': a 2-5 word name before the first comma."""
    m = _AUTHOR_START_RE.match(line.strip())
    return bool(m) and 2 <= len(m.group(1).split()) <= 5


def _authors_2017(block: list[str]) -> list[dict]:
    joined = " ".join(ln.strip() for ln in block)
    # An email wrapped at a hyphen or dot: "name@rwth- aachen.de".
    joined = re.sub(r"(@[\w.-]*[-.])\s+(?=\w)", r"\1", joined)
    out = []
    for entry in re.split(r"(?<=\S)\s*,?\s*" + EMAIL_RE.pattern + r"\s*,?", joined):
        entry = entry.strip(" ,")
        if not entry:
            continue
        name, _, aff = entry.partition(",")
        parts = [p.strip() for p in aff.split(",") if p.strip()]
        # "..., Country, Country": the form repeats the country.
        while len(parts) >= 2 and parts[-1] == parts[-2]:
            parts.pop()
        out.append({"name": text.clean_line(name), "affiliation": ", ".join(parts) or None})
    return out


def parse_2017(pages: list[str], meeting: dict, pdf_url: str) -> list[dict]:
    starts = []
    for i, t in enumerate(pages):
        head = t.split("\n", 3)
        if len(head) >= 3 and _SUB_RE.match(head[2].strip()) and "Rotterdam" in head[1]:
            starts.append(i)
    records = []
    for k, i in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(pages)
        first = pages[i].split("\n")
        session = text.clean_line(first[0])
        sub = int(_SUB_RE.match(first[2].strip()).group(1))
        lines = first[3:]
        for j in range(i + 1, end):
            lines.extend(pages[j].split("\n"))
        lines = [ln for ln in lines if ln.strip()]
        # Authors start at the first "Name, ..." line followed by an email soon after.
        a_at = next(
            (
                n
                for n in range(1, min(len(lines), 12))
                if _is_author_start(lines[n]) and any("@" in ln for ln in lines[n : n + 3])
            ),
            None,
        )
        if a_at is None:
            continue
        # Author lines end at the last email line, with at most two lines
        # (a wrapped affiliation) between one email line and the next.
        n, last = a_at, None
        while n < len(lines) and (last is None or n - last <= 3):
            if "@" in lines[n]:
                last = n
            n += 1
        n = (last if last is not None else a_at) + 1
        records.append(
            {
                "id": f"IP2017-{sub}",
                "year": 2017,
                "meeting": meeting["number"],
                "source": "book",
                "title": text.clean_line(" ".join(lines[:a_at])),
                "authors": _authors_2017(lines[a_at:n]),
                "presenters": [],
                "abstract": join_lines(lines[n:]),
                "format": "Other",
                "type": None,
                # The book names sessions only by number ("Minisymposium 2.17").
                "session_code": None,
                "session": session or None,
                "url": f"{pdf_url}#page={i + 1}",
                "attachments": [],
            }
        )
    return records


PARSERS = {2016: parse_2016, 2017: parse_2017}
