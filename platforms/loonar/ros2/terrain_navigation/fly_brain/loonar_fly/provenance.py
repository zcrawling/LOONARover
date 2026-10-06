"""Fail closed on a changed or incomplete original model/data installation."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify():
    manifest = json.loads((ROOT / "provenance.json").read_text())
    for relative, expected in manifest["sha256"].items():
        path = ROOT / relative
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise RuntimeError(f"Original model/data hash mismatch: {relative}")
    return manifest


if __name__ == "__main__":
    print(verify()["revision"])
