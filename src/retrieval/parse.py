# src/retrieval/parse.py

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from urllib.parse import urlparse

# PDF text extraction
try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None


class ParseError(RuntimeError):
    pass


def _clean_text(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _strip_html_to_text(html: str) -> str:
    """
    Minimal HTML -> text stripper (no external deps).
    Keeps headings somewhat readable.
    """
    # Remove scripts/styles
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", html)

    # Convert some block tags to newlines
    html = re.sub(r"(?is)</(p|div|br|li|h1|h2|h3|h4|tr|section)>", "\n", html)
    html = re.sub(r"(?is)<(h1|h2|h3|h4)[^>]*>", "\n", html)
    html = re.sub(r"(?is)<li[^>]*>", " - ", html)

    # Strip all remaining tags
    html = re.sub(r"(?is)<[^>]+>", "", html)

    # Decode a few common HTML entities (minimal)
    html = html.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'").replace("&quot;", '"')

    return _clean_text(html)


def _extract_pdf_pages(pdf_path: Path) -> List[str]:
    if PdfReader is None:
        raise ParseError("pypdf is not available. Install pypdf to parse PDFs.")

    reader = PdfReader(str(pdf_path))
    pages: List[str] = []
    for p in reader.pages:
        txt = p.extract_text() or ""
        pages.append(_clean_text(txt))
    return pages


def chunk_text(
    text: str,
    source_id: str,
    chunk_size: int = 1200,
    overlap: int = 200,
    loc: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Deterministic character-based chunker (simple, robust).
    Stores char offsets for citation alignment later.
    """
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks: List[Dict[str, Any]] = []
    n = len(text)
    start = 0
    idx = 1

    while start < n:
        end = min(start + chunk_size, n)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(
                {
                    "chunk_id": f"{source_id}_C{idx:04d}",
                    "source_id": source_id,
                    "text": chunk,
                    "char_start": start,
                    "char_end": end,
                    "loc": loc,  # e.g., "page:3" or "html"
                }
            )
            idx += 1
        if end == n:
            break
        start = end - overlap

    return chunks


def parse_one_raw(source_id: str, raw_path: Path, meta_path: Optional[Path], out_dir: Path) -> Tuple[Path, Path]:
    """
    Reads raw file (html/pdf), writes:
    - parsed text: {source_id}.txt
    - chunks json: {source_id}_chunks.json
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    suffix = raw_path.suffix.lower().lstrip(".")
    text = ""

    if suffix in ("html", "htm"):
        html = raw_path.read_text(encoding="utf-8", errors="replace")
        text = _strip_html_to_text(html)
        chunks = chunk_text(text, source_id=source_id, loc="html")

    elif suffix == "pdf":
        pages = _extract_pdf_pages(raw_path)
        # Join pages with page markers for later location reference
        joined_parts: List[str] = []
        page_chunks: List[Dict[str, Any]] = []

        for i, ptxt in enumerate(pages, start=1):
            marker = f"\n\n[PAGE {i}]\n"
            joined_parts.append(marker + ptxt)

            # Chunk per page to preserve page loc
            if ptxt.strip():
                page_chunks.extend(chunk_text(ptxt, source_id=source_id, loc=f"page:{i}"))

        text = _clean_text("\n".join(joined_parts))

        # If PDF had no extractable text, still create an empty chunks file
        chunks = page_chunks

    else:
        raise ParseError(f"Unsupported raw type for {raw_path.name} (expected .html or .pdf)")

    txt_path = out_dir / f"{source_id}.txt"
    chunks_path = out_dir / f"{source_id}_chunks.json"

    txt_path.write_text(text, encoding="utf-8")
    chunks_path.write_text(json.dumps(chunks, indent=2, sort_keys=True), encoding="utf-8")

    return txt_path, chunks_path


def parse_all_raw(raw_dir: Path, out_dir: Path) -> List[Tuple[str, str, str]]:
    """
    Parses all S*.html/pdf in raw_dir.
    Returns list of tuples: (source_id, txt_path, chunks_path)
    """
    outputs: List[Tuple[str, str, str]] = []

    for raw_path in sorted(raw_dir.glob("S*.html")) + sorted(raw_dir.glob("S*.pdf")):
        source_id = raw_path.stem  # "S001"
        meta_path = raw_dir / f"{source_id}.meta.json"
        if not meta_path.exists():
            meta_path = None

        txt_path, chunks_path = parse_one_raw(source_id, raw_path, meta_path, out_dir)
        outputs.append((source_id, str(txt_path), str(chunks_path)))

    return outputs
