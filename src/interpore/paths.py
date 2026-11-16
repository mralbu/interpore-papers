"""Filesystem layout shared by all pipeline stages.

Two trees with different publishing rules:

- ``data/`` is git-ignored and never published: the raw Indico exports, the
  downloaded books of abstracts, and every intermediate a stage caches.
- ``site/`` is the static site deployed to GitHub Pages. Only metadata,
  abstracts and derived data go there (never the book PDFs, slides or
  posters: the site links to them on interpore.org / events.interpore.org).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MEETINGS = ROOT / "meetings.yaml"  # hand-curated meeting history (committed)
TOPICS_YAML = ROOT / "topics.yaml"  # hand topic overrides (committed)

DATA_DIR = ROOT / "data"  # local-only stage outputs
RAW_DIR = DATA_DIR / "raw"
INDICO_DIR = RAW_DIR / "indico"  # data/raw/indico/<event id>.json (Indico export)
BOOKS_DIR = RAW_DIR / "books"  # data/raw/books/<year>.pdf
RECORDS = DATA_DIR / "records.json"  # one normalised record per abstract
RECORDS_REPORT = DATA_DIR / "records-report.txt"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"
TOPICS_DIR = DATA_DIR / "topics"

SITE_DIR = ROOT / "site"  # published static site
SITE_DATA_DIR = SITE_DIR / "data"  # generated: papers.json, topics.json, history.json

INDICO_BASE = "https://events.interpore.org"
