"""The hand-curated meeting list (``meetings.yaml``)."""

import datetime as dt
from functools import cache

import yaml

from interpore import paths


@cache
def load() -> dict:
    data = yaml.safe_load(paths.MEETINGS.read_text(encoding="utf-8"))
    for m in data["meetings"]:
        for k in ("start", "end"):
            if isinstance(m.get(k), dt.date):
                m[k] = m[k].isoformat()
    return data


def meetings() -> list[dict]:
    return load()["meetings"]


def by_year() -> dict[int, dict]:
    return {m["year"]: m for m in meetings()}
