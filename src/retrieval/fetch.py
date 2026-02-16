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


def fetch_many(
    urls: Iterable[str],
    out_dir: Path,
    allowlist: Allowlist,
    sleep_s: float = 0.25,
) -> List[FetchResult]:
    """
    Deterministically fetch URLs in the provided order.
    Writes raw + meta files under out_dir.
    """
    results: List[FetchResult] = []
    for i, url in enumerate(urls, start=1):
        source_id = make_source_id(i)
        res = fetch_one(url=url, source_id=source_id, out_dir=out_dir, allowlist=allowlist)
        results.append(res)
        if sleep_s:
            time.sleep(sleep_s)
    return results


def seed_urls_from_plan(plan: Dict[str, Any]) -> List[str]:
    """
    Simple seeding strategy:
    - take every topic's preferred_primary_urls
    - de-duplicate while preserving order
    """
    seen = set()
    urls: List[str] = []
    for topic in plan.get("topics", []):
        for u in topic.get("preferred_primary_urls", []) or []:
            if u not in seen:
                seen.add(u)
                urls.append(u)
    return urls
