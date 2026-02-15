import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

print("RUN_PIPELINE.PY STARTED")

CLIENT_PROFILE_PATH = Path("pipeline_artifacts/intake/ClientProfile_v1.json")
NOTES_LOG_PATH = Path("audit_logs/NotesLog.jsonl")

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def append_notes_log(event: dict) -> None:
    NOTES_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(NOTES_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

def load_client_profile() -> tuple[dict, str]:
    if not CLIENT_PROFILE_PATH.exists():
        raise FileNotFoundError(
            f"Client profile not found at: {CLIENT_PROFILE_PATH}\n"
            "Check filename + location under pipeline_artifacts/intake/"
        )

    with open(CLIENT_PROFILE_PATH, "r", encoding="utf-8") as f:
        client_profile = json.load(f)

    profile_hash = sha256_file(CLIENT_PROFILE_PATH)
    return client_profile, profile_hash

def main():
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
    # For now we just create an empty bundle so later stages have a file to read.
    retrieval_bundle = {
        "metadata": {
            "created_timestamp": datetime.now(timezone.utc).isoformat(),
            "pipeline_stage": "RAG Retrieval (stub)",
            "inputs": {
                "client_profile_sha256": profile_hash
            }
        },
        "items": []
    }

    out_path = Path("pipeline_artifacts/retrieval/RetrievalBundle.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(retrieval_bundle, f, indent=2)

    append_notes_log({
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "stage": "2_retrieval_stub",
    "artifact_path": str(out_path),
    "note": "Stub created; real allowlisted retrieval to be implemented next."
})
    
def main():
    print("MAIN FUNCTION EXECUTING")

    client_profile, profile_hash = load_client_profile()

    print("Stage 1 complete")
    print(profile_hash)


if __name__ == "__main__":
    main()

