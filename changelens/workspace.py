"""Editor documents, baseline comparison and UI-independent analysis orchestration."""
from dataclasses import asdict
import ast
import difflib
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import io
import os
import tempfile
import tokenize

from .core import (EXCLUDED, Snapshot, Symbol, app_dir, changed_symbols, checkpoint, decode_source,
                   ensure_fresh, impact_paths, index_repository, parse_file, save_snapshot, test_link_gaps, symbol_changed, configuration_seeds)
from .languages import language_for,is_source,is_config
from .ranking import graph_distances, rank_tests


class Document:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.raw = self.path.read_bytes()
        self.encoding = tokenize.detect_encoding(io.BytesIO(self.raw).readline)[0] if language_for(path)=="python" else "utf-8-sig" if self.raw.startswith(b'\xef\xbb\xbf') else "utf-8"
        self.text = decode_source(self.raw,path).replace("\r\n", "\n")
        self.newline = "\r\n" if b"\r\n" in self.raw else "\n"
        self.digest = hashlib.sha256(self.raw).hexdigest()

    def save(self, text: str):
        if not self.path.exists() or hashlib.sha256(self.path.read_bytes()).hexdigest() != self.digest:
            raise ValueError("This file changed outside the editor. Reopen it before saving to avoid overwriting those changes.")
        raw = text.replace("\n", self.newline).encode(self.encoding)
        self.save_raw(raw)

    def save_raw(self,raw,origin="save"):
        if not self.path.exists() or hashlib.sha256(self.path.read_bytes()).hexdigest()!=self.digest:
            raise ValueError("This file changed outside the editor. Reopen it before saving.")
        previous=self.raw
        previous_mode = self.path.stat().st_mode
        fd, name = tempfile.mkstemp(prefix=".changelens-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(name, previous_mode)
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        fresh=Document(self.path)
        self.__dict__.update(fresh.__dict__)
        self.history_warning=''
        try:
            from .change_history import record
            record(self.path,previous,raw,origin)
        except (OSError,sqlite3.Error) as exc:self.history_warning='Saved, but local history could not be recorded: '+str(exc)


def capture_baseline(snapshot: Snapshot):
    ensure_fresh(snapshot)
    files = {path: decode_source((Path(snapshot.root) / path).read_bytes(),path) for path, digest in snapshot.hashes.items()
             if digest not in {"oversized", "unreadable"}}
    record = {"schema":2,"snapshot": snapshot.id, "captured_at": time.time(), "files": files, "edges": snapshot.edges}
    with sqlite3.connect(app_dir() / "cache.sqlite3") as db:
        db.execute("CREATE TABLE IF NOT EXISTS baselines (root TEXT PRIMARY KEY, payload TEXT)")
        db.execute("INSERT OR REPLACE INTO baselines VALUES (?, ?)", (snapshot.root, json.dumps(record)))
    return record


def load_baseline(root: str):
    with sqlite3.connect(app_dir() / "cache.sqlite3") as db:
        db.execute("CREATE TABLE IF NOT EXISTS baselines (root TEXT PRIMARY KEY, payload TEXT)")
        row = db.execute("SELECT payload FROM baselines WHERE root=?", (str(Path(root).resolve()),)).fetchone()
    return json.loads(row[0]) if row else None


def automatic_comparison(snapshot):
    """Use Git when available; otherwise keep the first recorded source state."""
    if snapshot.revision != "no-head":
        return {"mode":"git", "label":"Changes since the latest Git commit", "created":False}
    baseline = load_baseline(snapshot.root)
    created = baseline is None
    if created:
        baseline = capture_baseline(snapshot)
    elif baseline.get("schema",1)<2:
        # Old releases never recorded non-Python files; do not pretend their prior state is known.
        baseline["files"].update({path:decode_source((Path(snapshot.root)/path).read_bytes(),path) for path,digest in snapshot.hashes.items()
            if language_for(path)!="python" and path not in baseline["files"] and digest not in {"oversized","unreadable"}})
        baseline["schema"]=2
        with sqlite3.connect(app_dir()/"cache.sqlite3") as db:db.execute("INSERT OR REPLACE INTO baselines VALUES (?, ?)",(snapshot.root,json.dumps(baseline)))
    return {"mode":"baseline", "label":"Changes since this folder was first recorded",
            "created":created, "captured_at":baseline["captured_at"],
            "note":"Earlier edits cannot be reconstructed without Git or a previously recorded state."}


def monitor_directories(root, cancel=None):
    paths = []
    for directory, dirs, _ in os.walk(root, followlinks=False):
        checkpoint(cancel)
        dirs[:] = sorted(name for name in dirs if name not in EXCLUDED and not (Path(directory)/name).is_symlink())
        paths.append(str(Path(directory)))
        if len(paths) >= 2048:
            break
    return paths


def baseline_changes(snapshot: Snapshot, baseline: dict, cancel=None):
    files, seeds, historical, warnings = [], set(), {}, []
    before = baseline["files"]
    after = {path: decode_source((Path(snapshot.root) / path).read_bytes(),path) for path, digest in snapshot.hashes.items()
             if digest not in {"oversized", "unreadable"}}
    for path in sorted(before.keys() | after.keys()):
        checkpoint(cancel)
        old, new = before.get(path, ""), after.get(path, "")
        if old == new:
            continue
        files.append({"path": path, "status": "deleted" if path not in after else "added" if path not in before else "modified",
                      "before": old, "after": new,
                      "diff": "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile="a/"+path, tofile="b/"+path))})
        if is_config(path):
            seeds.update(configuration_seeds(snapshot,path)); warnings.append(f"Configuration edit in {path}: included related source conservatively."); continue
        try:
            old_symbols = {s.id: s for s in parse_file(path, old)[0]}
        except SyntaxError:
            old_symbols = {}
        new_symbols = {sid: s for sid, s in snapshot.symbols.items() if s.path == path}
        for sid in old_symbols.keys() | new_symbols.keys():
            if sid not in old_symbols or sid not in new_symbols or symbol_changed(old_symbols[sid],new_symbols[sid]):
                seeds.add(sid)
                if sid not in new_symbols:
                    historical[sid] = asdict(old_symbols[sid])
        def module_statements(source):
            try:
                return [ast.dump(node) for node in ast.parse(source).body
                        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
            except SyntaxError:
                return None
        if language_for(path)=="python" and module_statements(old) != module_statements(new):
            seeds.update(new_symbols)
            warnings.append(f"Module-level edit in {path}: included its symbols conservatively.")
    edges = [{**edge, "kind": "historical_reference"} for edge in baseline.get("edges", [])
             if edge["callee"] in historical and edge["caller"] in snapshot.symbols]
    return {"files": files, "seeds": sorted(seeds), "historical_symbols": historical,
            "historical_edges": edges, "warnings": warnings}


def analyze_workspace(root: Path, seeds=None, comparison="auto", model_path=None, cancel=None, progress=lambda *_: None):
    started = time.perf_counter()
    snapshot = index_repository(root, cancel, progress)
    checkpoint(cancel)
    save_snapshot(snapshot)
    context = automatic_comparison(snapshot) if comparison == "auto" else {"mode":comparison,"label":"Git HEAD" if comparison=="git" else "Saved comparison point", "created":False}
    comparison = context["mode"]
    if isinstance(seeds, dict):
        matches = [symbol for symbol in snapshot.symbols.values()
                   if symbol.path == seeds["path"] and symbol.start <= seeds["line"] <= symbol.end]
        if not matches:
            raise ValueError("Place the cursor inside a function, class or source module, or choose a symbol from the Lens.")
        seeds = [min(matches, key=lambda symbol: symbol.end - symbol.start).id]
    if seeds is not None:
        selection_warnings=[]; expanded=[]
        for sid in seeds:
            symbol=snapshot.symbols.get(sid)
            if symbol and language_for(symbol.path) in {"java","csharp","go","rust"} and symbol.kind!="module":
                expanded.append(symbol.path+":<module>")
                selection_warnings.append(f"{sid}: structural analysis traces the containing file/module; symbol-level callers are unavailable.")
            else:expanded.append(sid)
        seeds=list(dict.fromkeys(expanded))
        missing = set(seeds) - snapshot.symbols.keys()
        if missing:
            raise ValueError("Selected symbol no longer exists. Select it again after reindexing.")
        changes = {"files": [], "seeds": seeds, "historical_symbols": {}, "historical_edges": [], "warnings": selection_warnings}
    elif comparison == "baseline":
        baseline = load_baseline(snapshot.root)
        if baseline is None:
            raise ValueError("Capture a baseline first, edit and save your code, then analyze changes.")
        changes = baseline_changes(snapshot, baseline, cancel)
    else:
        changes = changed_symbols(snapshot, cancel)
    merged = Snapshot(**{**snapshot.__dict__, "symbols": {**snapshot.symbols,
        **{sid: Symbol(**s) for sid, s in changes["historical_symbols"].items()}},
        "edges": snapshot.edges + changes["historical_edges"]})
    progress("Tracing affected code and identifying test evidence")
    impact = impact_paths(merged, changes["seeds"], cancel=cancel)
    ranking = rank_tests(merged, changes["seeds"], model_path=model_path, cancel=cancel) if changes["seeds"] else []
    gaps = test_link_gaps(merged, changes["seeds"], cancel)
    recommended = [row for row in ranking if row["recommended"]]
    report = {"snapshot": snapshot.id, "revision": snapshot.revision, "root": snapshot.root,
              "changes": changes, "impact": impact, "tests": ranking, "possible_gaps": gaps,
              "locations": {sid: {"path": s.path, "start": s.start, "end": s.end, "kind": s.kind,
                                   "is_test": s.is_test} for sid, s in merged.symbols.items()},
              "warnings": snapshot.warnings + changes["warnings"],
              "summary": {"changed_symbols": len(changes["seeds"]), "affected_symbols": len(impact),
                          "affected_files": len({merged.symbols[row["symbol"]].path for row in impact if row["symbol"] in merged.symbols}),
                          "recommended_tests": len(recommended), "all_test_candidates": len(ranking),
                          "direct_tests": sum(r["relation"] == "Direct caller" for r in recommended),
                          "inferred_tests": sum(r["relation"] == "Inferred dependency" for r in recommended),
                          "seconds": time.perf_counter() - started},
              "comparison": "symbol" if seeds is not None else comparison,
              "comparison_context":context,
              "profile":{key:value for key,value in snapshot.profile.items() if key in {"languages","frameworks","capabilities"}},
              "watch_directories":monitor_directories(snapshot.root, cancel),
              "ranking": {"method": ranking[0]["method"] if ranking else "no test candidates",
                          "policy": "Resolved paths first, inferred paths next; name-only matches require manual selection. Scores order tests within evidence groups."},
              "coverage_note": "Static references and explicitly labeled inferences. Dynamic behavior and fixture dependencies may be missing."}
    reachable={row['symbol'] for row in impact}
    report['relationships']=[edge for edge in merged.edges if edge['caller'] in reachable and edge['callee'] in reachable]
    return snapshot, report


def local_names(symbol: Symbol):
    from .python_source import symbol_node
    if language_for(symbol.path)!='python':return []
    try:
        fn = symbol_node(symbol)
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return []
        return sorted({node.id for statement in fn.body for node in ast.walk(statement)
                       if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)})
    except SyntaxError:
        return []
