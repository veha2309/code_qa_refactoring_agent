"""Generate deterministic integrity manifest for our own demo only."""
import hashlib
import json
from changelens.ranking import resources

if __name__ == "__main__":
    root = resources() / "demo"
    manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob("*.py"))}
    (resources() / "demo_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

