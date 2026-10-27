"""Explicit online preparation only. Fetch fixed release snapshots without running code."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import urllib.request
import zipfile

SOURCES = [("requests", "psf/requests", "v2.32.3"), ("flask", "pallets/flask", "3.1.0"), ("click", "pallets/click", "8.1.8")]


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "ChangeLens-academic-evaluation"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main():
    destination = Path("evaluation/repos")
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = Path("evaluation/public_snapshots.json")
    pinned = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    result = {}
    for name, repository, tag in SOURCES:
        sha = pinned[name]["commit"] if name in pinned else json.loads(fetch(f"https://api.github.com/repos/{repository}/commits/{tag}"))["sha"]
        raw = fetch(f"https://codeload.github.com/{repository}/zip/{sha}")
        archive_hash = hashlib.sha256(raw).hexdigest()
        if name in pinned and archive_hash != pinned[name]["archive_sha256"]:
            raise ValueError(f"Archive checksum mismatch for {name}")
        root = destination / name
        root.mkdir(exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for entry in archive.infolist():
                parts = PurePosixPath(entry.filename).parts[1:]
                if not parts or entry.is_dir():
                    continue
                if any(part in {"..", "."} or ":" in part or "\\" in part for part in parts):
                    raise ValueError("Unsafe archive path")
                target = root.joinpath(*parts)
                if not target.resolve().is_relative_to(root.resolve()):
                    raise ValueError("Archive escape rejected")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(entry))
        result[name] = {"repository": repository, "tag": tag, "commit": sha, "archive_sha256": archive_hash,
                        "url": f"https://github.com/{repository}/tree/{sha}", "execution": "never executed"}
        print(f"Fetched {name}: {sha}")
    manifest_path.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

