# src/retrieval/fetch.py

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from .allowlist import Allowlist


class FetchError(RuntimeError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def guess_ext(content_type: str, url: str) -> str:
    ct = (content_type or "").lower()
    if "pdf" in ct:
        return "pdf"
    if "html" in ct or "text/" in ct:
        return "html"
    # fallback: try url path
    path = urlparse(url).path.lower()
    if path.endswith(".pdf"):
        return "pdf"
    if path.endswith(".htm") or path.endswith(".html"):
        return "html"
    return "bin"


def make_source_id(i: int) -> str:
    return f"S{i:03d}"


@dataclass(frozen=True)
class FetchResult:
    source_id: str
    url: str
    final_url: str
    status_code: int
    content_type: str
    date_accessed_utc: str
    sha256: str
    raw_path: str
    meta_path: str


def fetch_one(
    url: str,
    source_id: str,
    out_dir: Path,
    allowlist: Allowlist,
    timeout_s: int = 30,
    user_agent: str = "GRAT_CRAT_AI_Pipeline/1.0",
) -> FetchResult:
    if not allowlist.is_allowed_url(url):
        raise FetchError(f"Blocked by allowlist: {url}")

    out_dir.mkdir(parents=True, exist_ok=True)

    headers = {"User-Agent": user_agent, "Accept": "*/*"}

    resp = requests.get(url, headers=headers, timeout=timeout_s, allow_redirects=True)
    status = int(resp.status_code)
    final_url = resp.url
    ct = resp.headers.get("Content-Type", "").split(";")[0].strip()

    if status >= 400:
        raise FetchError(f"HTTP {status} for {url}")

    raw = resp.content
    h = sha256_bytes(raw)
    accessed = utc_now_iso()
    ext = guess_ext(ct, final_url)

    raw_path = out_dir / f"{source_id}.{ext}"
    meta_path = out_dir / f"{source_id}.meta.json"

    raw_path.write_bytes(raw)

    meta: Dict[str, Any] = {
        "source_id": source_id,
        "url": url,
        "final_url": final_url,
        "date_accessed_utc": accessed,
        "http_status": status,
        "content_type": ct,
        "sha256": h,
        "bytes": len(raw),
        "raw_filename": raw_path.name,
        # optional helpful fields:
        "publisher_domain": urlparse(final_url).hostname,
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")

    return FetchResult(
        source_id=source_id,
        url=url,
        final_url=final_url,
        status_code=status,
        content_type=ct,
        date_accessed_utc=accessed,
        sha256=h,
        raw_path=str(raw_path),
        meta_path=str(meta_path),
    )


def _next_source_index(out_dir: Path) -> int:
    """
    Returns the next integer to use for a new source ID, based on the
    highest S-prefixed meta.json already present in out_dir.
    E.g. if S001–S007 exist, returns 8.
    File names are like S001.meta.json; p.stem would be 'S001.meta',
    so we split on '.' and take the first segment instead.
    """
    existing = [
        int(p.name.split(".")[0][1:])
        for p in out_dir.glob("S*.meta.json")
        if p.name.split(".")[0][1:].isdigit()
    ]
    return max(existing, default=0) + 1


def _already_fetched_urls(out_dir: Path) -> set:
    """
    Returns the set of original URLs already recorded in any S*.meta.json
    under out_dir. Used to skip re-fetching.
    """
    fetched: set = set()
    for meta_path in out_dir.glob("S*.meta.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            url = meta.get("url")
            if url:
                fetched.add(url)
            final_url = meta.get("final_url")
            if final_url:
                fetched.add(final_url)
        except (json.JSONDecodeError, OSError):
            continue
    return fetched


def fetch_many(
    urls: Iterable[str],
    out_dir: Path,
    allowlist: Allowlist,
    sleep_s: float = 0.25,
) -> List[FetchResult]:
    """
    Incrementally fetch URLs in the provided order.
    - Skips any URL whose original or final URL already appears in an
      existing S*.meta.json (idempotent re-runs are safe).
    - Continues source ID numbering from the highest existing S-prefixed
      file, so new sources are appended as S008, S009, … rather than
      overwriting S001–S007.
    Writes raw + meta files under out_dir.
    """
    already_fetched = _already_fetched_urls(out_dir)
    next_index = _next_source_index(out_dir)

    results: List[FetchResult] = []
    for url in urls:
        if url in already_fetched:
            continue
        source_id = make_source_id(next_index)
        next_index += 1
        res = fetch_one(url=url, source_id=source_id, out_dir=out_dir, allowlist=allowlist)
        already_fetched.add(res.url)
        already_fetched.add(res.final_url)
        results.append(res)
        if sleep_s:
            time.sleep(sleep_s)
    return results


def seed_urls_from_plan(plan: Dict[str, Any]) -> List[str]:
    """
    Collects every concrete URL to fetch from the plan, in order:
    - Each topic's preferred_primary_urls (explicit seed URLs)
    - De-duplicated while preserving insertion order
    To add new sources, add their URLs to preferred_primary_urls in the
    relevant topic inside RetrievalPlan_v1.json and re-run the fetcher.
    """
    seen = set()
    urls: List[str] = []
    for topic in plan.get("topics", []):
        for u in topic.get("preferred_primary_urls", []) or []:
            if u not in seen:
                seen.add(u)
                urls.append(u)
    return urls
