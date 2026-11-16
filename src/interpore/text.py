"""Text clean-up shared by the Indico and book parsers.

Abstract text is untrusted: it is cleaned to plain text with paragraphs
(``\\n\\n``) and inline math (``$...$``) kept; the site inserts it with
``textContent`` and renders only the math with KaTeX.
"""

import html
import re
import unicodedata

_TAG_BREAK_RE = re.compile(r"<\s*(br|/p|/div|/li|/h\d)\s*/?\s*>", re.I)
_TAG_RE = re.compile(r"<[^>]{0,500}>")
_MD_EMPH_RE = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1", re.S)
_SPACES_RE = re.compile(r"[ \t   ]+")

# Inline math as Indico renders it ($...$, $$...$$). Must agree with the JS
# MATH_SPLIT in site/app.js.
MATH_SPAN_RE = re.compile(r"\$\$.+?\$\$|(?<!\\)\$[^$\n]+?(?<!\\)\$", re.S)


def clean_abstract(raw: str | None) -> str:
    """HTML/markdown-ish abstract -> plain text with blank-line paragraphs."""
    if not raw:
        return ""
    t = raw.replace("\r\n", "\n").replace("\r", "\n")
    t = _TAG_BREAK_RE.sub("\n", t)
    t = _TAG_RE.sub("", t)
    t = html.unescape(t)
    t = _MD_EMPH_RE.sub(r"\2", t)
    t = unicodedata.normalize("NFC", t).replace("￾", "").replace("­", "")
    paras = []
    for block in re.split(r"\n\s*\n", t):
        lines = [_SPACES_RE.sub(" ", ln).strip() for ln in block.split("\n")]
        para = " ".join(ln for ln in lines if ln)
        if para:
            paras.append(para)
    return "\n\n".join(paras)


def clean_line(s: str | None) -> str:
    if not s:
        return ""
    s = html.unescape(_TAG_RE.sub("", s))
    s = unicodedata.normalize("NFC", s).replace("￾", "").replace("­", "")
    return _SPACES_RE.sub(" ", s.replace("\n", " ")).strip()


def plain(s: str) -> str:
    """Math markup dropped: for word counts, embeddings and keyword extraction."""
    return MATH_SPAN_RE.sub(" ", s)


def name_key(name: str) -> str:
    """Normalised author name for matching people across meetings: accents
    dropped, lower case, letters only ("Dorthe Wildenschild" -> "dorthe
    wildenschild"). Must agree with ``nameKey`` in site/app.js."""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return " ".join(re.findall(r"[a-z]+", s))


def word_count(s: str) -> int:
    return len(plain(s).split())
