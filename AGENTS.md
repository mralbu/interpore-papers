# InterPore Abstracts Explorer

A sibling of `sca-papers` (the SCA symposium explorer) for the annual meetings
of the International Society for Porous Media (InterPore): an interactive list
and topic map of the meetings' abstracts, plus a History view of the
conference since 2009. Published as a static site on GitHub Pages.

Audience: personal exploration.

## What is (and is not) available

- InterPore publishes **abstracts, not full papers**: the meetings collect
  abstracts (Indico's abstract module; earlier, books of abstracts with an
  ISSN), and no proceedings volume is linked from interpore.org. The
  society's journal (InterPore Journal, ipjournal.interpore.org) is separate.
  Some authors attach slides or posters on Indico; the site links them.
  Checked November 2026.
- **2018–2026**: every meeting runs on the society's Indico server
  (events.interpore.org, category "InterPore Annual Meetings"). Its public
  JSON export (`/export/event/<id>.json?detail=contributions`) gives every
  contribution with title, abstract (markdown with `$…$` math), authors and
  affiliations, presenter, presentation type, mini-symposium ("track") and
  attachments (slides/posters some authors upload). Indico event ids are in
  `meetings.yaml`. The export also lists a "Test Event" in the same category:
  it is not in `meetings.yaml`, so it is ignored.
- **2016, 2017**: before Indico; the books of abstracts are PDFs on
  interpore.org and are parsed (`books.py`). 2016 is LaTeX-generated
  (presenter, numbered affiliations, sections from the table of contents);
  2017 has one header per abstract with the submission number and session
  code but no session names.
- **2009–2015**: no abstracts online (the old WordPress event pages are gone
  since the site moved to Drupal; the booklets page starts at 2016). These
  meetings appear only in the History view, from `meetings.yaml`.
- Books of abstracts also exist for 2020–2024 and programmes for 2019–2024
  (linked from the History view); for those years the Indico export is the
  better source.

## Corpus facts

- 8,115 abstracts after filtering (Nov 2026): 2016 554, 2017 867, 2018 888,
  2019 934, 2020 620, 2021 688, 2022 507, 2023 889, 2024 741, 2025 528,
  2026 899. `data/records-report.txt` has the per-year table.
- Dropped: contributions with fewer than 25 words of abstract (placeholders)
  and, within a meeting, repeated title + first author (double submissions;
  the copy with a session is kept). About 25 in total.
- IDs: `IP<year>-<n>`, with n the Indico "friendly id" (the number in the
  contribution URL is a different, database id), the 2017 submission number,
  or the 2016 printed page number.
- Presentation formats are normalised to Invited / Oral / Poster / Online /
  Other ("Not recorded" on the site). 2019 has no type for ~450
  contributions; 2016/2017 books record none. Invited = track or type says
  invited/plenary/keynote.
- Mini-symposium codes are renumbered every year (MS10 in 2024 is not MS10
  in 2025): a session filter is always (year, name).
- pypdfium2 text of the books: `\r\n` line ends, `￾` for soft hyphens,
  some lost `ff` ligatures ("e ects"). Paragraph breaks are guessed (short
  line ending a sentence).
- 2016 affiliations come from a form ("Position, Organisation, address…,
  country code"); `_POSITION_RE` decides whether the first field is a job
  title. 2017 author lines carry emails: they are used to split authors and
  then dropped.

## Decisions

- **Publishing boundary**: titles, authors, affiliations, abstracts (switch:
  `INCLUDE_ABSTRACTS` in `site.py`), sessions, links. Never emails, Indico
  email hashes, the book PDFs or attachment files (the site links to Indico
  and interpore.org). Abstracts belong to their authors; every entry links to
  its source.
- Same pipeline shape as `sca-papers`, minus what abstracts don't need: no
  PDF conversion, no figures, no citation graph (abstracts have no reference
  lists to match), no LLM summaries (abstracts are already short summaries;
  everything on the site is the authors' text plus derived data).
- **Embeddings**: bge-m3 (as in sca-papers) on title + abstract, 512 tokens.
  On Linux the PyPI torch wheel is used (pulls CUDA libs, ~3 GB); CPU is fine
  for ~8k abstracts (~1 h on 4 cores; minutes on a GPU or MPS).
- **Topics**: same UMAP + HDBSCAN (leaf) + c-TF-IDF code as sca-papers,
  `MIN_CLUSTER_SIZE = 45`, `MIN_SAMPLES = 8` for the bigger corpus. Topic
  names are hand-written in `topics.yaml` (`rename: {id: {name, short}}`)
  after reading each cluster's keywords and titles; ids only hold while the
  inputs are unchanged, so re-check after a rebuild.
- **Related abstracts** in the reading pane: 8 nearest neighbours by
  embedding, and "Same authors" (other abstracts sharing an author name,
  matched by `text.name_key` / `nameKey` in app.js: accents dropped, lower
  case, letters only; spelling variants are missed).
- **History view**: `meetings.yaml` (hand-curated, every fact from
  interpore.org or Indico pages; sources listed at its top) + statistics
  computed with polars in `history.py` + Vega-Lite charts built with Altair
  (`site/data/charts/*.json`). The front end embeds them with vega-embed and
  injects a theme config (the dataviz skill's default palette, light and dark
  steps); "Not recorded" is drawn in neutral grey. Charts: abstracts per
  meeting by format, returning vs first-seen authors, themes over time (small
  multiples of keyword-match shares, `TERMS`), topic share by year (heatmap).
  Each chart has a data-table fallback.
- **Site**: plain JS, no build step (adapted from sca-papers' app.js).
  `papers.json` (metadata, ~5 MB) loads first; `abstracts.json` (~17 MB,
  gzip on Pages) loads in the background, then search is rebuilt to include
  abstracts. CDN libraries pinned with SRI: deck.gl, MiniSearch, KaTeX,
  vega, vega-lite, vega-embed.
- Network: fetching needs events.interpore.org and interpore.org; the
  embedding model comes from Hugging Face.

## Layout

- `src/interpore/`: `paths.py` (every directory), `cache.py` (atomic
  writes), `meetings.py` (loads `meetings.yaml`), `fetch.py`, `indico.py`,
  `books.py`, `text.py` (clean-up, name keys, math spans), `records.py`,
  `embed.py`, `topics.py`, `history.py`, `site.py`, `llms.py`, `cli.py`
  (`interpore <stage>`).
- `data/` (git-ignored): `raw/indico/<event>.json`, `raw/books/<year>.pdf`,
  `records.json`, `records-report.txt`, `embeddings/<model>/`,
  `topics/topics.json`.
- `site/` (published): `index.html`, `app.js`, `style.css`, generated
  `data/` (`papers.json`, `abstracts.json`, `topics.json`, `history.json`,
  `charts/`), `llms.txt`, `llms-full.txt`, `llms/`.

## Conventions

- Python with `uv`; polars for data frames, Altair for charts.
- Each stage is a `just` recipe and is cached/resumable.
- Raw downloads (Indico exports, book PDFs) are untrusted data.
- `just check` runs pytest and ruff.
- No Claude co-authorship or attribution in commits or PRs (as in sca-papers).
