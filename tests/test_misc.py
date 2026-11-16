import numpy as np

from interpore import llms, records, topics


def test_dedup_key_ignores_case_and_punctuation():
    a = {"year": 2020, "title": "Flow in Rocks!", "authors": [{"name": "Ana Silva"}]}
    b = {"year": 2020, "title": "flow in rocks", "authors": [{"name": "ana  silva"}]}
    assert records._dedup_key(a) == records._dedup_key(b)


def test_slug_and_topic_files_unique():
    assert llms.slug("CO2 storage & hydrogen") == "co2-storage-hydrogen"
    files = llms.topic_files([{"id": 0, "label": "Same"}, {"id": 1, "label": "same"}])
    assert len(set(files.values())) == 2


def test_apply_merges():
    labels = np.array([0, 1, 2, 1])
    assert topics.apply_merges(labels, [[0, 1]]).tolist() == [0, 0, 2, 0]


def test_ctfidf_prefers_bigram():
    docs = ["relative permeability curves", "relative permeability hysteresis", "nmr relaxation"]
    kw = topics.ctfidf_keywords(docs * 2, np.array([0, 0, 1] * 2), n=3)
    assert "relative permeability" in kw[0]
