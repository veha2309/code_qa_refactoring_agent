import json
from pathlib import Path

from changelens.core import index_repository
from changelens.ranking import evaluate

if __name__ == "__main__":
    labels = json.loads(Path("evaluation/public_labels.json").read_text(encoding="utf-8"))
    results = {}
    for name in ("requests", "flask", "click"):
        snapshot = index_repository(Path("evaluation/repos") / name)
        cases = [case for case in labels["cases"] if case["repository"] == name]
        results[name] = evaluate(snapshot, cases)
        results[name]["parse_and_resolution_warnings"] = snapshot.warnings
        print(f"{name}: " + json.dumps([{k: v for k, v in r.items() if k != "cases"} for r in results[name]["results"]]))
    Path("evaluation/public_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

