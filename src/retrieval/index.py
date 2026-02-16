# src/retrieval/index.py

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class IndexError(RuntimeError):
    pass


@dataclass
class VectorIndex:
    vectorizer: TfidfVectorizer
    matrix: Any  # scipy sparse matrix
    chunks: List[Dict[str, Any]]  # aligned with rows in matrix


def load_all_chunks(parsed_dir: Path) -> List[Dict[str, Any]]:
    chunk_files = sorted(parsed_dir.glob("S*_chunks.json"))
    if not chunk_files:
        raise IndexError(f"No chunk files found in: {parsed_dir}")

    chunks: List[Dict[str, Any]] = []
    for fp in chunk_files:
        raw = fp.read_text(encoding="utf-8", errors="replace").strip()
        if not raw:
            continue
        data = json.loads(raw)

        # data is list of chunk dicts
        for c in data:
            if not c.get("text"):
                continue
            chunks.append(c)

    if not chunks:
        raise IndexError("Loaded chunk files but no chunks contained text.")
    return chunks


def build_index(parsed_dir: Path, out_dir: Path) -> Path:
    """
    Builds TF-IDF index over all chunks. Writes:
      - out_dir/index.pkl
    Returns path to index.pkl
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    chunks = load_all_chunks(parsed_dir)
    texts = [c["text"] for c in chunks]

    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        max_features=200_000,
        ngram_range=(1, 2),
    )
    matrix = vectorizer.fit_transform(texts)

    idx = VectorIndex(vectorizer=vectorizer, matrix=matrix, chunks=chunks)

    out_path = out_dir / "index.pkl"
    out_path.write_bytes(pickle.dumps(idx))
    return out_path


def load_index(index_path: Path) -> VectorIndex:
    if not index_path.exists():
        raise IndexError(f"Index not found: {index_path}")
    return pickle.loads(index_path.read_bytes())


def search(index: VectorIndex, query: str, k: int = 8) -> List[Dict[str, Any]]:
    if not query or not query.strip():
        return []

    q_vec = index.vectorizer.transform([query])
    sims = cosine_similarity(q_vec, index.matrix).ravel()

    if k <= 0:
        k = 1
    k = min(k, len(index.chunks))

    # top-k indices by similarity
    top_idx = sims.argsort()[-k:][::-1]

    results: List[Dict[str, Any]] = []
    for i in top_idx:
        c = dict(index.chunks[int(i)])  # copy
        c["score"] = float(sims[int(i)])
        results.append(c)
    return results
