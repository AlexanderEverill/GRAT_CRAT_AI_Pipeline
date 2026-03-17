from pathlib import Path
from src.retrieval.index import build_index, load_index, search


def test_build_and_search_index(tmp_path: Path):
    # Create a tiny parsed_dir with one chunks file
    parsed_dir = tmp_path / "parsed"
    parsed_dir.mkdir(parents=True)

    (parsed_dir / "S001_chunks.json").write_text(
        """
        [
          {"chunk_id":"S001_C0001","source_id":"S001","text":"IRC 2702 defines qualified interests for GRATs.","char_start":0,"char_end":50,"loc":"html"},
          {"chunk_id":"S001_C0002","source_id":"S001","text":"Charitable remainder annuity trusts are under IRC 664.","char_start":51,"char_end":110,"loc":"html"}
        ]
        """.strip(),
        encoding="utf-8",
    )

    out_dir = tmp_path / "index"
    index_path = build_index(parsed_dir, out_dir)
    idx = load_index(index_path)

    hits = search(idx, "qualified interest IRC 2702", k=1)
    assert len(hits) == 1
    assert hits[0]["source_id"] == "S001"
    assert "score" in hits[0]
