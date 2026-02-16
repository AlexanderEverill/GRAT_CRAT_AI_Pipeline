# src/retrieval/bundle.py

from __future__ import annotations

import json
import re
from dataclasses import dataclass
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


def build_bundle(
    plan_path: Path,
    index_path: Path,
    raw_dir: Path,
    out_dir: Path,
) -> Tuple[Path, Path]:
    plan = load_plan(plan_path)
    idx = load_index(index_path)

    allow_domains = {normalize_host(d) for d in plan["allowlist"]["domains"]}

    # --- Build Citation Manifest as we go ---
    citations: List[Dict[str, Any]] = []
    cite_key_counter = 1

    items: List[Dict[str, Any]] = []

    for topic in plan.get("topics", []):
        topic_id = topic["topic_id"]
        topic_items: List[Dict[str, Any]] = []

        # We will aggregate key points for this topic across query hits
        key_points: List[Dict[str, Any]] = []

        for qobj in topic.get("queries", []):
            q = qobj["q"]
            k = int(qobj.get("k", 8))
            hits = search(idx, q, k=k)

            for h in hits:
                source_id = h["source_id"]
                meta = _load_meta(raw_dir, source_id)

                final_url = meta.get("final_url") or meta.get("url") or ""
                title = meta.get("title") or meta.get("page_title") or f"{source_id}"
                date_accessed = meta.get("date_accessed_utc") or meta.get("date_accessed") or ""

                host = normalize_host(urlparse(final_url).hostname or meta.get("publisher_domain") or "")
                if host and not any(host == d or host.endswith("." + d) for d in allow_domains):
                    # should not happen if fetch allowlist worked, but fail-closed
                    continue

                quote = _word_limit_quote(h.get("text", ""), 25)
                loc = h.get("loc") or meta.get("loc") or "unknown"

                cite_key = f"[S{cite_key_counter}]"
                cite_key_counter += 1

                citations.append(
                    {
                        "cite_key": cite_key,
                        "source_id": source_id,
                        "url": final_url,
                        "loc": loc,
                    }
                )

                key_points.append(
                    {
                        "claim": f"Evidence for topic {topic_id} (query: {q})",
                        "quote": quote,
                        "loc": loc,
                        "cite_key": cite_key,
                        "chunk_id": h.get("chunk_id"),
                        "score": h.get("score"),
                    }
                )

        # De-duplicate key_points by (source_id, quote) to avoid repeats
        seen = set()
        deduped: List[Dict[str, Any]] = []
        for kp in key_points:
            key = (kp.get("chunk_id"), kp.get("quote"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(kp)

        # Choose publisher_domain/title/url from best available meta among hits
        # (simple approach: first hit with meta)
        chosen_meta = {}
        for kp in deduped:
            sid = kp.get("chunk_id", "").split("_")[0] or kp.get("source_id", "")
            if sid:
                m = _load_meta(raw_dir, sid)
                if m.get("final_url") or m.get("url"):
                    chosen_meta = m
                    break

        chosen_url = chosen_meta.get("final_url") or chosen_meta.get("url") or ""
        chosen_host = normalize_host(urlparse(chosen_url).hostname or chosen_meta.get("publisher_domain") or "")

        items.append(
            {
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
                    }
                    for kp in deduped
                ],
            }
        )

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
