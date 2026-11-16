"""Entry point: ``uv run interpore <stage>``. Each stage is also a just recipe."""

import argparse
import json


def fetch(args: argparse.Namespace) -> None:
    """Download the Indico exports (2018 on) and the 2016/2017 books of abstracts."""
    from interpore import fetch as stage

    print("\n".join(stage.run(force=args.force, refresh=args.refresh)))


def records(args: argparse.Namespace) -> None:
    """Parse the raw sources into data/records.json (one record per abstract)."""
    from interpore import records as stage

    recs, report = stage.run()
    if args.ids:
        for r in recs:
            if r["id"] in args.ids:
                print(json.dumps(r, ensure_ascii=False, indent=1))
        return
    print(report, end="")


def embed(args: argparse.Namespace) -> None:
    """Embed title + abstract with a local model (resumable)."""
    from interpore import embed as stage

    done, total = stage.run(args.model or stage.DEFAULT_MODEL)
    print(f"embedded {done} new/changed of {total}")


def topics(args: argparse.Namespace) -> None:
    """UMAP map, HDBSCAN topics and c-TF-IDF labels (overrides in topics.yaml)."""
    from interpore import embed as embed_stage
    from interpore import topics as stage

    data = stage.run(model=args.model or embed_stage.DEFAULT_MODEL, force=args.force)
    print(stage.table(data), end="")


def site(args: argparse.Namespace) -> None:
    """Export site/data/ (papers, abstracts, topics, history, charts) and llms.txt."""
    from interpore import site as stage

    print(stage.run(), end="")


def main() -> None:
    parser = argparse.ArgumentParser(prog="interpore", description=__doc__)
    stages = parser.add_subparsers(dest="stage", required=True)
    p = stages.add_parser("fetch", help=fetch.__doc__)
    p.add_argument("--force", action="store_true", help="download everything again")
    p.add_argument("--refresh", action="store_true", help="re-download the Indico exports")
    p.set_defaults(func=fetch)
    p = stages.add_parser("records", help=records.__doc__)
    p.add_argument("ids", nargs="*", help="print these records")
    p.set_defaults(func=records)
    p = stages.add_parser("embed", help=embed.__doc__)
    p.add_argument("--model", help="embedding model (default: bge-m3)")
    p.set_defaults(func=embed)
    p = stages.add_parser("topics", help=topics.__doc__)
    p.add_argument("--model", help="embedding model to use (default: bge-m3)")
    p.add_argument("--force", action="store_true", help="recompute even if fresh")
    p.set_defaults(func=topics)
    stages.add_parser("site", help=site.__doc__).set_defaults(func=site)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
