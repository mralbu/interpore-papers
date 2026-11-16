# InterPore Abstracts Explorer

[![Site](https://img.shields.io/badge/site-mralbu.github.io-2a78d6)](https://mralbu.github.io/interpore-papers/)
[![Abstracts](https://img.shields.io/badge/abstracts-8%2C115-2a78d6)](https://events.interpore.org/)
[![Years](https://img.shields.io/badge/years-2016%E2%80%932026-2a78d6)](https://www.interpore.org/annual-meetings)
[![Deploy](https://github.com/mralbu/interpore-papers/actions/workflows/pages.yml/badge.svg)](https://github.com/mralbu/interpore-papers/actions/workflows/pages.yml)

An interactive explorer for the abstracts of the annual meetings of the
International Society for Porous Media (InterPore): 8,115 abstracts from
eleven meetings, 2016–2026, as a list, a topic map and a History view of the
conference since its first meeting in 2009. A sibling of
[sca-papers](https://github.com/mralbu/sca-papers).

## Abstracts, not papers

InterPore meetings collect **abstracts only**; there are no full papers or
proceedings to link to. What is online:

| Meetings | Source | In the explorer |
| --- | --- | --- |
| 2018–2026 | [events.interpore.org](https://events.interpore.org/) (Indico) public JSON export | every abstract, with authors, affiliations, presenter, mini-symposium, format, and links to slides/posters some authors uploaded |
| 2016, 2017 | books of abstracts (PDF) on interpore.org | every abstract, parsed from the PDF; each links to its page in the book |
| 2009–2015 | nothing online | History view only (dates, places, notes) |

## Features

- **List and map views.** A list (newest, oldest, title, best match) and a 2D
  map of the abstracts clustered into 39 topics from text embeddings (bge-m3).
- **Search and filters.** Full-text search over titles, authors,
  affiliations, sessions and abstracts; year range; presentation format;
  topic; a single mini-symposium (click a session in the reading pane or the
  History view).
- **Reading pane.** Title, authors with affiliations (presenter marked), the
  mini-symposium, the abstract (math rendered with KaTeX), a link to the
  abstract on Indico or in the book, uploaded slides/posters, similar
  abstracts and other abstracts by the same authors.
- **History.** Every meeting since 2009 on a timeline (place, dates, format,
  notes, links to the Indico event, book of abstracts, programme), with
  per-meeting numbers (abstracts, sessions, authors, share of first-time
  authors, distinctive two-word terms, largest sessions) and charts: abstracts
  per meeting by format, returning vs new authors, themes over time (hydrogen
  storage, machine learning, CO2 storage, …) and topic shares by year.
- `llms.txt`, per-topic `llms/*.txt` and `llms-full.txt` for language models.

## What is published

Titles, authors and affiliations, abstracts, sessions, formats and links,
plus derived data (topics, map coordinates, similar-abstract links,
statistics). Never emails, the book PDFs or uploaded files: the site links to
events.interpore.org and interpore.org. The abstracts belong to their authors.

## Quick start

```sh
just setup        # Python environment (uv)
just fetch        # Indico exports + 2016/2017 books into data/raw/ (cached)
just build        # records, embeddings (bge-m3), topics, site data
just serve        # preview at http://localhost:8000
```

`just update` re-downloads the Indico exports and rebuilds (use it while a
meeting's programme is still changing, or to add a new meeting after adding
it to `meetings.yaml`). Every stage is cached, so only new or changed
abstracts are re-embedded.

## Pipeline

| Stage | Recipe | Output |
| --- | --- | --- |
| 0 | `fetch` | `data/raw/indico/<event>.json`, `data/raw/books/<year>.pdf` |
| 1 | `records` | `data/records.json` (one record per abstract), `data/records-report.txt` |
| 2 | `embed` | `data/embeddings/bge-m3/` |
| 3 | `topics` | `data/topics/topics.json` (UMAP map, HDBSCAN topics, c-TF-IDF keywords; names in `topics.yaml`) |
| 4 | `site-data` | `site/data/` (`papers.json`, `abstracts.json`, `topics.json`, `history.json`, `charts/`), `site/llms*.txt` |

`meetings.yaml` is the hand-curated list of meetings (with sources) that
drives both the fetch stage and the History view. `data/` is git-ignored;
only `site/` is published.

## Publishing

CI does not run the pipeline, so `site/data/` is committed. After a rebuild,
commit `site/` and push to `main`; `.github/workflows/pages.yml` checks the
published file types and sizes and deploys to GitHub Pages (Settings → Pages →
Source: GitHub Actions).

## Development

`just check` runs pytest and ruff. Design notes, source quirks and decisions
are in [AGENTS.md](AGENTS.md).
