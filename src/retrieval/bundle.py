# src/retrieval/bundle.py

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from .allowlist import normalize_host
from .index import load_index, search, VectorIndex
from .plan import load_plan


def _word_limit_quote(text: str, max_words: int = 25) -> str:
    words = re.findall(r"\S+", text.strip())
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words])


def _load_meta(raw_dir: Path, source_id: str) -> Dict[str, Any]:
    meta_path = raw_dir / f"{source_id}.meta.json"
    if not meta_path.exists():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _build_source_citation_map(
    raw_dir: Path,
    allow_domains: set,
) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
    """Build a 1:1 citation map: one cite key per source document.

    Returns (source_id_to_cite_key, citations_list).
    Scans all *.meta.json files in raw_dir and creates [S001]...[SNNN]
    keyed by the source_id stored in each meta file.
    """
    source_to_cite: Dict[str, str] = {}
    citations: List[Dict[str, Any]] = []

    meta_files = sorted(raw_dir.glob("S*.meta.json"))
    for meta_path in meta_files:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        source_id = meta.get("source_id", "")
        if not source_id:
            continue

        final_url = meta.get("final_url") or meta.get("url") or ""
        host = normalize_host(
            urlparse(final_url).hostname or meta.get("publisher_domain") or ""
        )
        if host and not any(host == d or host.endswith("." + d) for d in allow_domains):
            continue

        cite_key = f"[{source_id}]"
        source_to_cite[source_id] = cite_key
        citations.append({
            "cite_key": cite_key,
            "source_id": source_id,
            "url": final_url,
            "title": meta.get("title") or meta.get("page_title") or source_id,
            "publisher_domain": host or "unknown",
            "date_accessed": meta.get("date_accessed_utc") or meta.get("date_accessed") or "",
            "loc": "html",
        })

    return source_to_cite, citations


def build_bundle(
    plan_path: Path,
    index_path: Path,
    raw_dir: Path,
    out_dir: Path,
) -> Tuple[Path, Path]:
    plan = load_plan(plan_path)
    idx = load_index(index_path)

    allow_domains = {normalize_host(d) for d in plan["allowlist"]["domains"]}

    # One cite key per source document (e.g. [S001], [S002], ...)
    source_to_cite, citations = _build_source_citation_map(raw_dir, allow_domains)

    items: List[Dict[str, Any]] = []

    for topic in plan.get("topics", []):
        topic_id = topic["topic_id"]

        key_points: List[Dict[str, Any]] = []

        for qobj in topic.get("queries", []):
            q = qobj["q"]
            k = int(qobj.get("k", 8))
            hits = search(idx, q, k=k)

            for h in hits:
                source_id = h["source_id"]
                if source_id not in source_to_cite:
                    continue

                meta = _load_meta(raw_dir, source_id)
                quote = _word_limit_quote(h.get("text", ""), 25)
                loc = h.get("loc") or meta.get("loc") or "unknown"

                key_points.append({
                    "claim": f"Evidence for topic {topic_id} (query: {q})",
                    "quote": quote,
                    "loc": loc,
                    "cite_key": source_to_cite[source_id],
                    "source_id": source_id,
                    "chunk_id": h.get("chunk_id"),
                    "score": h.get("score"),
                })

        # De-duplicate key_points by (chunk_id, quote)
        seen: set = set()
        deduped: List[Dict[str, Any]] = []
        for kp in key_points:
            key = (kp.get("chunk_id"), kp.get("quote"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(kp)

        # Choose publisher_domain/title/url from best available meta among hits
        chosen_meta: Dict[str, Any] = {}
        for kp in deduped:
            sid = kp.get("source_id", "")
            if sid:
                m = _load_meta(raw_dir, sid)
                if m.get("final_url") or m.get("url"):
                    chosen_meta = m
                    break

        chosen_url = chosen_meta.get("final_url") or chosen_meta.get("url") or ""
        chosen_host = normalize_host(
            urlparse(chosen_url).hostname or chosen_meta.get("publisher_domain") or ""
        )

        items.append({
            "source_id": topic_id,
            "title": f"Topic bundle: {topic_id}",
            "url": chosen_url,
            "publisher_domain": chosen_host if chosen_host else "unknown",
            "date_accessed": chosen_meta.get("date_accessed_utc") or "",
            "relevance_tags": [topic_id],
            "reliability_tier": "PRIMARY",
            "key_points": [
                {
                    "claim": kp["claim"],
                    "quote": kp["quote"],
                    "loc": kp["loc"],
                    "cite_key": kp["cite_key"],
                    "source_id": kp["source_id"],
                }
                for kp in deduped
            ],
        })

    bundle = {
        "bundle_version": "1.0",
        "client_context_hash": None,
        "items": items,
    }

    manifest = {
        "manifest_version": "1.0",
        "citation_style": "inline-short-id",
        "citations": citations,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = out_dir / "RetrievalBundle_v1.json"
    manifest_path = out_dir / "CitationsManifest_v1.json"

    bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    return bundle_path, manifest_path
