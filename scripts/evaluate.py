from pathlib import Path
import argparse
import json

from changelens.core import index_repository
from changelens.ranking import evaluate, resources

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=resources() / "demo")
    parser.add_argument("--labels", type=Path, default=resources() / "demo_labels.json")
    parser.add_argument("--output", type=Path, default=Path("evaluation/demo_results.json"))
    args = parser.parse_args()
    result = evaluate(index_repository(args.root), json.loads(args.labels.read_text(encoding="utf-8"))["cases"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))

