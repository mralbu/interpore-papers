"""Stage: abstract embeddings (local model, CUDA/MPS/CPU).

Per abstract the embedded text is title + abstract (math markup dropped).
Output in ``data/embeddings/<model>/``: ``vectors.npy`` (float32,
L2-normalised, one row per abstract), ``ids.json`` (row order) and
``hashes.json`` (sha of the embedded text). Re-runs only embed abstracts
whose text changed, so adding a new meeting embeds only that meeting.

bge-m3 is the default, as in the SCA explorer: multilingual, 8k context,
no remote code. Abstracts are short (median ~290 words), so 512 tokens
covers nearly all of them.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from interpore import cache, paths, records, text

BATCH_SIZE = 16


@dataclass(frozen=True)
class Model:
    name: str
    hf_id: str
    max_seq_length: int = 512


MODELS = {m.name: m for m in [Model("bge-m3", "BAAI/bge-m3")]}
DEFAULT_MODEL = "bge-m3"


def document_text(r: dict) -> str:
    return f"{r['title']}\n\n{text.plain(r['abstract'])}".strip()


def model_dir(name: str) -> Path:
    return paths.EMBEDDINGS_DIR / name


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def load(name: str = DEFAULT_MODEL) -> tuple[list[str], np.ndarray]:
    d = model_dir(name)
    ids = json.loads((d / "ids.json").read_text())
    return ids, np.load(d / "vectors.npy")


def _device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    return "mps" if torch.backends.mps.is_available() else "cpu"


def run(name: str = DEFAULT_MODEL) -> tuple[int, int]:
    """Embed every abstract with ``name``; returns (embedded now, total)."""
    model = MODELS[name]
    texts = {r["id"]: document_text(r) for r in records.load()}
    d = model_dir(name)
    old: dict[str, np.ndarray] = {}
    old_hashes: dict[str, str] = {}
    if (d / "hashes.json").exists() and (d / "vectors.npy").exists():
        old_hashes = json.loads((d / "hashes.json").read_text())
        ids, vecs = load(name)
        old = dict(zip(ids, vecs, strict=True))
    hashes = {i: _sha(t) for i, t in texts.items()}
    todo = [i for i in texts if old_hashes.get(i) != hashes[i] or i not in old]
    if todo:
        from sentence_transformers import SentenceTransformer

        st = SentenceTransformer(model.hf_id, device=_device())
        st.max_seq_length = model.max_seq_length
        # Longest first keeps padding low within each batch.
        todo.sort(key=lambda i: len(texts[i]), reverse=True)
        new = st.encode(
            [texts[i] for i in todo],
            batch_size=BATCH_SIZE,
            normalize_embeddings=True,
            show_progress_bar=True,
            convert_to_numpy=True,
        )
        old.update(zip(todo, new.astype(np.float32), strict=True))
    ids = sorted(texts)
    vectors = np.stack([old[i] for i in ids]).astype(np.float32)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / ".vectors.tmp.npy"
    np.save(tmp, vectors)
    tmp.replace(d / "vectors.npy")
    cache.write_json_atomic(d / "ids.json", ids)
    cache.write_json_atomic(d / "hashes.json", {i: hashes[i] for i in ids})
    return len(todo), len(ids)
