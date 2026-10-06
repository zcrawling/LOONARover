"""Fetch exact upstream revisions; never reset or overwrite an existing checkout."""
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

from loonar_fly.provenance import ROOT, verify


def main():
    manifest = json.loads((ROOT / "provenance.json").read_text())
    vendor = ROOT / "vendor"
    vendor.mkdir(exist_ok=True)
    repo = vendor / "fly-brain"
    if not repo.exists():
        subprocess.run(["git", "init", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", manifest["repository"]], check=True)
        subprocess.run(["git", "-C", str(repo), "fetch", "--depth=1", "origin", manifest["revision"]], check=True)
        subprocess.run(["git", "-C", str(repo), "checkout", "--detach", "FETCH_HEAD"], check=True)
    revision = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    if revision != manifest["revision"]:
        raise SystemExit("Existing vendor checkout differs from pinned revision; preserved without reset")
    annotations = vendor / "neuron_annotations.tsv"
    if not annotations.exists():
        data = urllib.request.urlopen(manifest["annotations_url"], timeout=60).read()
        if hashlib.sha256(data).hexdigest() != manifest["sha256"]["vendor/neuron_annotations.tsv"]:
            raise SystemExit("Downloaded annotation checksum mismatch")
        temporary = annotations.with_suffix(".download")
        temporary.write_bytes(data)
        temporary.replace(annotations)
    verify()
    print("Verified exact original model and FlyWire data:", revision)


if __name__ == "__main__":
    main()
