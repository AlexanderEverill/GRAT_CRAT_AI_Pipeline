import json
import hashlib
from pathlib import Path
from typing import Tuple
from datetime import datetime, timezone

print("RUN_PIPELINE.PY STARTED")

# Always anchor paths to the project root (one level above /src)
BASE_DIR = Path(__file__).resolve().parent.parent
CLIENT_PROFILE_PATH = BASE_DIR / "pipeline_artifacts" / "intake" / "ClientProfile_v1.json"
NOTES_LOG_PATH = BASE_DIR / "audit_logs" / "NotesLog.jsonl"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def append_notes_log(event: dict) -> None:
    NOTES_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with NOTES_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def load_client_profile() -> Tuple[dict, str]:
    if not CLIENT_PROFILE_PATH.exists():
        raise FileNotFoundError(
            f"Client profile not found at: {CLIENT_PROFILE_PATH}\n"
            "Check filename + location under pipeline_artifacts/intake/"
        )

    raw = CLIENT_PROFILE_PATH.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError(
            f"Client profile file exists but is empty (did you forget to save it?): {CLIENT_PROFILE_PATH}"
        )

    try:
        client_profile = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Client profile JSON is invalid: {CLIENT_PROFILE_PATH} ({e})") from e

    profile_hash = sha256_file(CLIENT_PROFILE_PATH)
    return client_profile, profile_hash


def main() -> None:
    # -------- Stage 1: Intake --------
    client_profile, profile_hash = load_client_profile()

    append_notes_log({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": "1_client_intake",
        "artifact_path": str(CLIENT_PROFILE_PATH),
        "artifact_sha256": profile_hash,
        "profile_version": client_profile.get("metadata", {}).get("profile_version"),
    })

    print("✅ Stage 1 complete: ClientProfile loaded")
    print("   SHA256:", profile_hash)

    # -------- Stage 2 (stub): Retrieval --------
    retrieval_bundle = {
        "metadata": {
            "created_timestamp": datetime.now(timezone.utc).isoformat(),
            "pipeline_stage": "RAG Retrieval (stub)",
            "inputs": {"client_profile_sha256": profile_hash},
        },
        "items": [],
    }

    out_path = BASE_DIR / "pipeline_artifacts" / "retrieval" / "RetrievalBundle.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(retrieval_bundle, indent=2), encoding="utf-8")

    append_notes_log({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": "2_retrieval_stub",
        "artifact_path": str(out_path),
        "note": "Stub created; real allowlisted retrieval to be implemented next.",
    })

    print("✅ Stage 2 complete: RetrievalBundle stub written")
    print("   Path:", out_path)


if __name__ == "__main__":
    main()


