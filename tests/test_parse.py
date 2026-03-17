from pathlib import Path
import json

from src.retrieval.parse import parse_one_raw


def test_parse_html_creates_txt_and_chunks(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    out_dir = tmp_path / "parsed"
    raw_dir.mkdir()

    html_path = raw_dir / "S001.html"
    html_path.write_text("<html><body><h1>Title</h1><p>Hello world.</p></body></html>", encoding="utf-8")

    txt_path, chunks_path = parse_one_raw("S001", html_path, None, out_dir)

    assert txt_path.exists()
    assert chunks_path.exists()

    txt = txt_path.read_text(encoding="utf-8")
    assert "Title" in txt
    assert "Hello world" in txt

    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    assert len(chunks) >= 1
    assert chunks[0]["source_id"] == "S001"
    assert "char_start" in chunks[0]
    assert "char_end" in chunks[0]
