"""History view data: per-meeting statistics and charts.

Writes ``site/data/history.json`` (society facts, every meeting from
``meetings.yaml`` with its links, and for meetings with abstracts: counts by
format, mini-symposia, authors, first-time authors, distinctive terms, largest
sessions, most over-represented topics) and Vega-Lite specs built with Altair
in ``site/data/charts/*.json``. Chart colours and fonts are left to the front
end, which injects a theme config for light and dark mode (including the
2px surface-coloured gap between bar segments and heatmap cells).

Counts are of accepted abstracts in the public record (Indico export or book of
abstracts), not of registered participants.
"""

import re
from collections import Counter

import altair as alt
import numpy as np
import polars as pl

from interpore import cache, meetings, paths, text, topics

HISTORY_JSON = paths.SITE_DATA_DIR / "history.json"
CHARTS_DIR = paths.SITE_DATA_DIR / "charts"

FORMATS = ["Invited", "Oral", "Poster", "Online", "Other"]
FORMAT_LABELS = {"Other": "Not recorded"}

# Themes followed over time: share of abstracts whose title or abstract matches.
TERMS = {
    "Hydrogen storage": r"\bhydrogen\b|\bh2\b|\bh_2\b",
    "Machine learning": r"machine learning|deep learning|neural network|\bcnn\b|\bpinns?\b|"
    r"physics-informed|artificial intelligence|\bai\b",
    "CO2 storage": r"\bco2\b|\bco_2\b|carbon dioxide|carbon capture|carbon storage|"
    r"sequestration",
    "Geothermal": r"geotherm",
    "Microfluidics": r"microfluidic|micromodel",
    "Batteries & fuel cells": r"batter(y|ies)|fuel cell|electrolys|electrode",
    "Biology & biofilms": r"biofilm|bacteri|microb|tissue|biolog|living cells|tumou?r",
    "Imaging (CT, synchrotron, NMR)": r"micro-?ct|x-ray|synchrotron|tomograph|\bnmr\b|\bmri\b",
    "Pore-network models": r"pore[- ]network",
    "Lattice Boltzmann": r"lattice[- ]boltzmann|\blbm\b",
    "Phase-field": r"phase[- ]field",
    "Fractures": r"fractur",
}


def _authors_by_year(recs: list[dict]) -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    for r in recs:
        out.setdefault(r["year"], set()).update(
            k for a in r["authors"] if (k := text.name_key(a["name"]))
        )
    return out


def frame(recs: list[dict], papers: list[dict]) -> pl.DataFrame:
    topic_of = {p["id"]: p["topic"] for p in papers}
    return pl.DataFrame(
        {
            "id": [r["id"] for r in recs],
            "year": [r["year"] for r in recs],
            "format": [r["format"] for r in recs],
            "session": [r["session"] or "" for r in recs],
            "n_authors": [len(r["authors"]) for r in recs],
            "topic": [topic_of.get(r["id"], -1) for r in recs],
            "doc": [f"{r['title']}. {text.plain(r['abstract'])}" for r in recs],
        }
    )


def meeting_stats(recs: list[dict], papers: list[dict], topic_list: list[dict]) -> dict:
    df = frame(recs, papers)
    years = sorted(df["year"].unique().to_list())
    names = {t["id"]: t.get("short") or t["label"] for t in topic_list}
    authors = _authors_by_year(recs)
    seen: set[str] = set()
    year_terms = distinctive_terms(df["doc"].to_list(), df["year"].to_list())
    overall = df.group_by("topic").len().with_columns(share=pl.col("len") / df.height)
    overall_share = dict(zip(overall["topic"], overall["share"], strict=True))
    out = {}
    for y in years:
        d = df.filter(pl.col("year") == y)
        fmt = Counter(d["format"].to_list())
        sessions = Counter(s for s in d["session"].to_list() if s)
        by_topic = d.group_by("topic").len()
        lift = sorted(
            (
                (n / d.height / overall_share[t], t, n)
                for t, n in zip(by_topic["topic"], by_topic["len"], strict=True)
                if n >= 10 and t >= 0
            ),
            reverse=True,
        )
        people = authors.get(y, set())
        out[y] = {
            "abstracts": d.height,
            "formats": {f: fmt[f] for f in FORMATS if fmt.get(f)},
            "sessions": len(sessions),
            "authors": len(people),
            "new_authors": len(people - seen) if seen else None,
            "mean_authors": round(float(d["n_authors"].mean()), 2),
            "terms": year_terms.get(y, [])[:8],
            "top_sessions": [{"name": s, "n": n} for s, n in sessions.most_common(5)],
            "top_topics": [
                {"id": int(t), "name": names.get(t, str(t)), "n": int(n), "lift": round(x, 2)}
                for x, t, n in lift[:3]
            ],
        }
        seen |= people
    return out


# Words that make a two-word term about writing rather than subject
# ("good agreement", "remains challenging", "providing insight").
FILLER = {
    "good", "agreement", "improve", "strongly", "affect", "available", "literature",
    "compared", "traditional", "reveal", "distinct", "complex", "promising", "solution",
    "critical", "optimizing", "poorly", "understood", "mechanisms", "governing", "remains",
    "challenging", "https", "http", "doi", "www", "com", "providing", "insight", "insights",
    "predictive", "capability", "efficient", "single", "distribution", "solid", "deformation",
    "inlet", "outlet", "temperature", "physical", "permeability", "phase", "fluid", "strong",
    "great", "significance", "paper", "approach", "pivotal", "crucial", "enabling",
    "taken", "account", "highlight", "potential", "remain", "insufficiently", "particular",
    "attention", "address", "challenge", "managed", "operated", "contract", "ntess", "doe",
}  # fmt: skip


def distinctive_terms(
    docs: list[str], years: list[int], n: int = 8, min_docs: int = 8
) -> dict[int, list[str]]:
    """Per year, the two-word terms most over-represented in that year's
    abstracts (single words pick up writing style more than subject: "pivotal",
    "crucial"). Score: extra share of abstracts using the term times the log of
    its lift over all years, among terms used by at least ``min_docs``
    abstracts that year."""
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, CountVectorizer

    vec = CountVectorizer(
        ngram_range=(2, 2),
        binary=True,
        min_df=10,
        stop_words=sorted(ENGLISH_STOP_WORDS | topics.DOMAIN_STOPWORDS),
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9\-]+\b",
    )
    x = vec.fit_transform(docs).tocsc()
    terms = vec.get_feature_names_out()
    years_arr = np.array(years)
    overall = np.asarray(x.sum(axis=0)).ravel() / len(docs)
    out = {}
    for y in sorted(set(years)):
        rows = years_arr == y
        df_y = np.asarray(x[rows].sum(axis=0)).ravel()
        share = df_y / rows.sum()
        lift = np.maximum(share, 1e-9) / np.maximum(overall, 1e-9)
        # Extra share of abstracts using the term, weighted by how unusual it is:
        # frequent topical terms beat rare one-off words.
        score = np.where((df_y >= min_docs) & (lift > 1.3), (share - overall) * np.log(lift), 0)
        picked: list[str] = []
        for i in np.argsort(-score):
            if score[i] <= 0:
                break
            if set(terms[i].split()) & FILLER or any(c.isdigit() for c in terms[i]):
                continue  # writing style, or funding boilerplate ("contract de-na0003525")
            term = terms[i]
            if set(term.split()) & {w for p in picked for w in p.split()}:
                continue  # one term per word: no "co2 storage" next to "co2 injection"
            picked.append(term)
            if len(picked) == n:
                break
        out[y] = picked
    return out


# --- charts --------------------------------------------------------------------


def chart_abstracts(recs: list[dict]) -> alt.Chart:
    df = pl.DataFrame({"year": [r["year"] for r in recs], "format": [r["format"] for r in recs]})
    counts = (
        df.group_by("year", "format")
        .len()
        .with_columns(
            pl.col("format").replace(FORMAT_LABELS).alias("Format"),
            pl.col("format").replace({f: i for i, f in enumerate(FORMATS)}).cast(int).alias("o"),
        )
        .rename({"len": "Abstracts", "year": "Year"})
        .sort("Year", "o")
    )
    order = [FORMAT_LABELS.get(f, f) for f in FORMATS]
    return (
        alt.Chart(alt.Data(values=counts.to_dicts()))
        .mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
        .encode(
            x=alt.X("Year:O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("sum(Abstracts):Q", title="Abstracts"),
            color=alt.Color("Format:N", sort=order, scale=alt.Scale(domain=order)),
            order=alt.Order("o:Q"),
            tooltip=[
                alt.Tooltip("Year:O"),
                alt.Tooltip("Format:N"),
                alt.Tooltip("sum(Abstracts):Q", title="Abstracts"),
            ],
        )
        .properties(width="container", height=260)
    )


def chart_authors(stats: dict) -> alt.Chart:
    rows = []
    for y, s in sorted(stats.items()):
        if s["new_authors"] is None:
            rows.append({"Year": y, "Authors": s["authors"], "Group": "First seen", "o": 1})
            continue
        rows.append({"Year": y, "Authors": s["new_authors"], "Group": "First seen", "o": 1})
        rows.append(
            {"Year": y, "Authors": s["authors"] - s["new_authors"], "Group": "Returning", "o": 0}
        )
    order = ["Returning", "First seen"]
    return (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
        .encode(
            x=alt.X("Year:O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("sum(Authors):Q", title="Distinct authors"),
            color=alt.Color("Group:N", sort=order, scale=alt.Scale(domain=order), title=None),
            order=alt.Order("o:Q"),
            tooltip=["Year:O", "Group:N", alt.Tooltip("sum(Authors):Q", title="Authors")],
        )
        .properties(width="container", height=240)
    )


def chart_topics(recs: list[dict], papers: list[dict], topic_list: list[dict]) -> alt.Chart:
    df = frame(recs, papers).filter(pl.col("topic") >= 0)
    names = {t["id"]: t["label"] for t in topic_list}
    per_year = df.group_by("year").len().rename({"len": "total"})
    share = (
        df.group_by("year", "topic")
        .len()
        .join(per_year, on="year")
        .with_columns(
            (pl.col("len") / pl.col("total") * 100).round(1).alias("Share"),
            pl.col("topic").replace_strict(names, return_dtype=pl.String).alias("Topic"),
        )
        .rename({"year": "Year", "len": "Abstracts"})
    )
    # Topics in map order is meaningless; sort by the year of peak share so the
    # rows read as a timeline (older themes on top, rising ones at the bottom).
    peak = (
        share.sort("Share", descending=True)
        .group_by("Topic", maintain_order=True)
        .first()
        .sort("Year", "Share")
    )
    order = peak["Topic"].to_list()
    return (
        alt.Chart(alt.Data(values=share.select("Year", "Topic", "Share", "Abstracts").to_dicts()))
        .mark_rect(cornerRadius=2)
        .encode(
            x=alt.X("Year:O", title=None, axis=alt.Axis(labelAngle=0, orient="top")),
            y=alt.Y("Topic:N", sort=order, title=None, axis=alt.Axis(labelLimit=260)),
            color=alt.Color(
                "Share:Q",
                title="% of the year's abstracts",
                legend=alt.Legend(orient="bottom", gradientLength=220),
            ),
            tooltip=[
                "Topic:N",
                "Year:O",
                alt.Tooltip("Share:Q", title="% of abstracts", format=".1f"),
                "Abstracts:Q",
            ],
        )
        .properties(width="container", height=alt.Step(17))
    )


def term_shares(recs: list[dict]) -> list[dict]:
    rows = []
    years = sorted({r["year"] for r in recs})
    docs = {
        y: [f"{r['title']} {r['abstract']}".lower() for r in recs if r["year"] == y] for y in years
    }
    for term, pattern in TERMS.items():
        rx = re.compile(pattern)
        for y in years:
            n = sum(bool(rx.search(d)) for d in docs[y])
            rows.append(
                {"Term": term, "Year": y, "Share": round(100 * n / len(docs[y]), 1), "Abstracts": n}
            )
    return rows


def chart_terms(recs: list[dict]) -> alt.Chart:
    rows = term_shares(recs)
    # Small multiples (one panel per theme, one colour): no legend to decode.
    base = alt.Chart(alt.Data(values=rows)).encode(
        x=alt.X("Year:O", title=None, axis=alt.Axis(labelAngle=0, values=[2016, 2020, 2024])),
        y=alt.Y("Share:Q", title="% of abstracts"),
    )
    line = base.mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=28, filled=True))
    hover = base.mark_point(size=400, opacity=0).encode(
        tooltip=["Term:N", "Year:O", alt.Tooltip("Share:Q", title="% of abstracts"), "Abstracts:Q"]
    )
    return (
        alt.layer(line, hover)
        .properties(width=150, height=105)
        .facet(facet=alt.Facet("Term:N", title=None, sort=list(TERMS)), columns=4)
        .resolve_scale(y="independent")
    )


def write(recs: list[dict], papers: list[dict], topic_list: list[dict]) -> list:
    stats = meeting_stats(recs, papers, topic_list)
    data = meetings.load()
    meeting_list = []
    for m in data["meetings"]:
        m = dict(m)
        if m.get("indico"):
            m["indico_url"] = f"{paths.INDICO_BASE}/event/{m['indico']}/"
        if m["year"] in stats:
            m["stats"] = stats[m["year"]]
        meeting_list.append(m)
    with_stats = [m for m in meeting_list if "stats" in m]
    all_people = set().union(*_authors_by_year(recs).values())
    totals = {
        "abstracts": len(recs),
        "meetings": len(data["meetings"]) - sum(bool(m.get("upcoming")) for m in data["meetings"]),
        "meetings_with_abstracts": len(with_stats),
        "first_year_with_abstracts": min(m["year"] for m in with_stats),
        "authors": len(all_people),
        "countries": len(
            {
                m.get("country")
                for m in data["meetings"]
                if m.get("country") and not m.get("upcoming")
            }
        ),
    }
    out = {"society": data["society"], "totals": totals, "meetings": meeting_list}
    cache.write_json_atomic(HISTORY_JSON, out)
    charts = {
        "abstracts": chart_abstracts(recs),
        "authors": chart_authors(stats),
        "topics": chart_topics(recs, papers, topic_list),
        "terms": chart_terms(recs),
    }
    files = [HISTORY_JSON]
    for name, chart in charts.items():
        spec = chart.to_dict()
        spec.pop("config", None)
        path = CHARTS_DIR / f"{name}.json"
        cache.write_json_atomic(path, spec)
        files.append(path)
    return files


def lift_table(stats: dict) -> str:
    """Plain-text summary, for the CLI."""
    rows = [f"{'year':>4} {'abs':>5} {'auth':>5} {'new':>5} {'ms':>3}  terms"]
    for y, s in sorted(stats.items()):
        rows.append(
            f"{y:>4} {s['abstracts']:>5} {s['authors']:>5} {s['new_authors'] or '':>5} "
            f"{s['sessions']:>3}  {', '.join(s['terms'][:6])}"
        )
    return "\n".join(rows) + "\n"
