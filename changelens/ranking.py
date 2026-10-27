"""Small supervised ranker with portable JSON coefficients, never pickle."""
from __future__ import annotations

from collections import deque
import json
import math
from pathlib import Path
import re
import sys
import time
import tracemalloc

from .core import Snapshot, checkpoint, index_repository, impact_paths
from .languages import language_for
from .polyglot import INFERRED_KINDS

FEATURES = ["lexical_overlap", "symbol_overlap", "path_overlap", "same_module_reference", "inverse_graph_distance"]


def resources() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "resources"


def words(text: str) -> set[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return {x.lower() for x in re.findall(r"[A-Za-z][A-Za-z0-9]*", text) if len(x) > 1} - {"def", "return", "assert", "test", "from", "import", "self"}


def overlap(a: set, b: set) -> float:
    return len(a & b) / max(1, len(a | b))


def feature_vector(snapshot: Snapshot, seeds: list[str], test_id: str, distances: dict[str, int]) -> list[float]:
    test = snapshot.symbols[test_id]
    selected = [snapshot.symbols[s] for s in seeds if s in snapshot.symbols]
    text = " ".join(s.source for s in selected)
    names = " ".join(s.name for s in selected)
    paths = " ".join(s.path for s in selected)
    seed_modules = {s.path for s in selected}
    module_ref = any(e["caller"] == test_id and snapshot.symbols[e["callee"]].path in seed_modules for e in snapshot.edges)
    distance = distances.get(test_id)
    return [overlap(words(text), words(test.source)), overlap(words(names), words(test.name)),
            overlap(words(paths), words(test.path)), float(module_ref),
            1.0 / (1 + distance) if distance is not None else 0.0]


def graph_distances(snapshot: Snapshot, seeds: list[str], cancel=None) -> dict[str, int]:
    reverse = {}
    for edge in snapshot.edges:
        checkpoint(cancel)
        reverse.setdefault(edge["callee"], []).append(edge["caller"])
    distances, queue = {}, deque((s, 0) for s in seeds)
    while queue:
        checkpoint(cancel)
        node, distance = queue.popleft()
        if node in distances:
            continue
        distances[node] = distance
        queue.extend((s, distance + 1) for s in reverse.get(node, []))
    return distances


def load_model(path: Path | None = None):
    try:
        model = json.loads((path or resources() / "starter_model.json").read_text(encoding="utf-8"))
        if model["features"] != FEATURES or len(model["coefficients"]) != len(FEATURES):
            return None
        if not all(math.isfinite(float(v)) for v in model["coefficients"] + [model["intercept"]]):
            return None
        return model
    except (OSError, ValueError, KeyError, TypeError):
        return None


def rank_tests(snapshot: Snapshot, seeds: list[str], method="learned", model_path: Path | None = None,
               cancel=None) -> list[dict]:
    model = load_model(model_path) if method == "learned" else None
    mode = "learned logistic regression" if model else ("keyword baseline" if method == "keyword" else "structural fallback" if method == "learned" else "structural baseline")
    distances = graph_distances(snapshot, seeds, cancel)
    evidence = {row["symbol"]: row for row in impact_paths(snapshot, seeds, cancel=cancel)}
    selected = [snapshot.symbols[s] for s in seeds if s in snapshot.symbols]
    text_words = words(" ".join(s.source for s in selected))
    name_words = words(" ".join(s.name for s in selected))
    path_words = words(" ".join(s.path for s in selected))
    seed_modules = {s.path for s in selected}
    module_callers = {edge["caller"] for edge in snapshot.edges if snapshot.symbols[edge["callee"]].path in seed_modules}
    rows = []
    for sid, symbol in snapshot.symbols.items():
        checkpoint(cancel)
        if not symbol.is_test:
            continue
        distance = distances.get(sid)
        values = [overlap(text_words, words(symbol.source)), overlap(name_words, words(symbol.name)),
                  overlap(path_words, words(symbol.path)), float(sid in module_callers),
                  1 / (1 + distance) if distance is not None else 0.0]
        row_mode=mode
        if model and (language_for(symbol.path)=="python" or method!="learned"):
            z = model["intercept"] + sum(a * b for a, b in zip(model["coefficients"], values))
            score = 1 / (1 + math.exp(-max(-500, min(500, z))))
        elif method == "keyword":
            score = values[0]
        else:
            score = values[4] + .1 * values[3] + .05 * values[1]
            if method=="learned" and language_for(symbol.path)!="python":row_mode="structural ranking (non-Python; learned scores not validated)"
        trace = evidence.get(sid, {})
        inferred = any(e["kind"] in INFERRED_KINDS for e in trace.get("evidence", []))
        if distance is not None:
            fixture = any(edge["kind"] == "fixture_dependency" for edge in trace.get("evidence", []))
            relation = "Inferred dependency" if inferred else "Fixture dependency" if fixture else "Direct caller" if distance == 1 else "Transitive caller" if distance else "Changed test"
            via = [snapshot.symbols[s].name for s in trace.get("path", []) if s in snapshot.symbols]
            reason = " -> ".join(via)
            if inferred:
                reason += ". Includes a conservative scope, callback or receiver inference."
        elif values[1] >= .12:
            relation, reason = "Name similarity", "Shares meaningful words with the changed symbol; no dependency path was resolved."
        else:
            relation, reason = "Weak match", "No dependency path or strong symbol-name match. Not recommended by default."
        rows.append({"symbol": sid, "score": score, "method": row_mode, "features": dict(zip(FEATURES, values)),
                     "language":language_for(symbol.path),"model_scope":"Structural ranking used here. The starter learned model was trained on Python examples and is not applied to this language." if language_for(symbol.path)!="python" else "Python synthetic starter model",
                     "distance": distance, "relation": relation, "reason": reason,
                     "recommended": distance is not None,
                     "tier": 1 if inferred else 0 if distance is not None else 2 if relation == "Name similarity" else 3,
                     "evidence": trace.get("evidence", []),
                     "note": "Ranking score, not calibrated confidence"})
    # Keep baselines raw for evaluation; production learned/fallback ranking respects evidence.
    return sorted(rows, key=lambda row: ((row["tier"],) if method == "learned" else ()) + (-row["score"], row["symbol"]))


def train_model(output: Path, cancel=None, progress=lambda *_: None) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn import __version__ as sklearn_version
    dataset = json.loads((resources() / "training_labels.json").read_text(encoding="utf-8"))
    snapshot = index_repository(resources() / "training_repo", cancel, progress)
    x, y = [], []
    for case in dataset["cases"]:
        checkpoint(cancel)
        seeds = case["seeds"]
        distances = graph_distances(snapshot, seeds)
        for sid, symbol in snapshot.symbols.items():
            if symbol.is_test:
                x.append(feature_vector(snapshot, seeds, sid, distances))
                y.append(int(sid in case["relevant_tests"]))
    progress(f"Fitting logistic regression on {len(y)} synthetic labeled pairs")
    estimator = LogisticRegression(random_state=42, class_weight="balanced", max_iter=1000)
    checkpoint(cancel)
    estimator.fit(x, y)
    checkpoint(cancel)
    model = {"schema_version": 1, "dataset_version": dataset["version"], "features": FEATURES,
             "coefficients": estimator.coef_[0].tolist(), "intercept": float(estimator.intercept_[0]),
             "training_pairs": len(y), "positive_pairs": sum(y), "sklearn_version": sklearn_version,
             "training_snapshot": snapshot.id, "seed": 42,
             "limitations": "Synthetic starter data only; scores are not calibrated confidence."}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(model, indent=2), encoding="utf-8")
    return model


def evaluate(snapshot: Snapshot, cases: list[dict], model_path: Path | None = None, cancel=None) -> dict:
    results = []
    for method in ("keyword", "structural", "learned"):
        tracemalloc.start()
        start = time.perf_counter()
        rows = []
        for case in cases:
            checkpoint(cancel)
            missing = [s for s in case["seeds"] + case["relevant_tests"] if s not in snapshot.symbols]
            if missing or not case["relevant_tests"]:
                rows.append({"id": case["id"], "supported": False, "missing": missing})
                continue
            ranking = rank_tests(snapshot, case["seeds"], method, model_path, cancel)
            truth = set(case["relevant_tests"])
            ordered = [r["symbol"] for r in ranking]
            matches = [i + 1 for i, sid in enumerate(ordered) if sid in truth]
            distances = graph_distances(snapshot, case["seeds"])
            rows.append({"id": case["id"], "supported": True,
                         "has_resolved_test_path": any(sid in distances for sid in truth),
                         "recall_at_5": len(set(ordered[:5]) & truth) / len(truth),
                         "reciprocal_rank": 1 / matches[0] if matches else 0,
                         "top_5": ordered[:5]})
        elapsed = time.perf_counter() - start
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        supported = [r for r in rows if r["supported"]]
        results.append({"method": method, "effective_method": "structural fallback" if method == "learned" and not load_model(model_path) else method,
                        "supported": len(supported), "unsupported": len(rows) - len(supported),
                        "recall_at_5": sum(r["recall_at_5"] for r in supported) / len(supported) if supported else None,
                        "mrr": sum(r["reciprocal_rank"] for r in supported) / len(supported) if supported else None,
                        "seconds": elapsed, "peak_traced_python_bytes": peak, "cases": rows})
    return {"snapshot": snapshot.id, "results": results,
            "limitations": "Static relevance evaluation. Python allocation peak excludes native allocations. Not a Copilot comparison."}

