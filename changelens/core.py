"""Static analysis only. Target repository modules are never imported."""
from __future__ import annotations

import ast
import difflib
import hashlib
import io
import json
import keyword
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tokenize
import textwrap
from collections import deque
from dataclasses import asdict, dataclass, field
from threading import Event
from typing import Callable
from .languages import is_source, is_indexable, is_config, language_for, project_profile

EXCLUDED = {".git", ".venv", "venv", "env", "node_modules", "__pycache__", "build", "dist", ".tox", ".mypy_cache", ".pytest_cache", ".runtime", ".ropeproject", ".idea"}
EXCLUDED.update({".next",".nuxt",".svelte-kit","target","obj",".gradle","coverage",".angular",".output"})
EXCLUDED.update({'.python-packages','.python_packages','__pypackages__','site-packages','.ruff_cache','.uv','.conda','.pixi'})
EXCLUDED.update({'.dart_tool','.pub-cache','.flutter-plugins','Pods','.symlinks'})
MAX_BYTES = 2_000_000


class Cancelled(Exception):
    pass


def checkpoint(cancel: Event | None):
    if cancel is not None and cancel.is_set():
        raise Cancelled("Operation cancelled")


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "--no-pager", "-c", "core.quotepath=false", "-c", "core.fsmonitor=false", "-C", str(root), *args],
                            capture_output=True, timeout=20, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
                            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", "replace").strip() or "Git command failed")
    return result.stdout.decode("utf-8", "replace")


def app_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "ChangeLens"
    base.mkdir(parents=True, exist_ok=True)
    return base


def python_files(root: Path, cancel: Event | None = None):
    for current, dirs, files in os.walk(root, followlinks=False):
        checkpoint(cancel)
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not (Path(current) / d).is_symlink())
        for filename in sorted(files):
            path = Path(current) / filename
            if path.suffix == ".py" and not path.is_symlink():
                yield path


def fingerprint(root: Path, cancel: Event | None = None) -> dict[str, str]:
    result = {}
    for current,dirs,files in os.walk(root,followlinks=False):
        checkpoint(cancel)
        dirs[:]=sorted(name for name in dirs if name not in EXCLUDED and not (Path(current)/name).is_symlink())
        for filename in sorted(files):
            path=Path(current)/filename
            if not is_indexable(path) or path.is_symlink():continue
            try:
                result[path.relative_to(root).as_posix()]="oversized" if path.stat().st_size>MAX_BYTES else hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:result[path.relative_to(root).as_posix()]="unreadable"
    return result


def revision(root: Path) -> str:
    try:
        return git(root, "rev-parse", "HEAD").strip()
    except (ValueError, OSError, subprocess.TimeoutExpired):
        return "no-head"


def decode_source(raw: bytes,path=None) -> str:
    if path is not None and language_for(path)!="python":return raw.decode("utf-8-sig")
    encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
    return raw.decode(encoding)


@dataclass
class Symbol:
    id: str
    path: str
    name: str
    qualname: str
    kind: str
    start: int
    end: int
    source: str
    is_test: bool = False
    change_key: str = ""
    start_byte: int = -1
    end_byte: int = -1


@dataclass
class Snapshot:
    root: str
    revision: str
    hashes: dict[str, str]
    symbols: dict[str, Symbol]
    edges: list[dict]
    warnings: list[str]
    id: str
    profile: dict = field(default_factory=dict)


def parse_file(path: str, source: str, definition_nodes=None) -> tuple[list[Symbol], list[tuple], list[tuple]]:
    if language_for(path)!="python":
        if not is_source(path):return [],[],[]
        from .syntax import parse_unit
        unit=parse_unit(path,source)
        return unit.symbols,[(caller,expression,line) for caller,expression,line,_,_ in unit.calls],[]
    tree = ast.parse(source, filename=path)
    lines = source.splitlines(keepends=True)
    symbols, calls, imports = [], [], []

    class Extractor(ast.NodeVisitor):
        def __init__(self):
            self.scope = []
            self.owner = None
            self.anonymous = 0

        def definition(self, node, kind):
            qualified = ".".join(self.scope + [node.name])
            sid = f"{path}:{qualified}"
            if definition_nodes is not None:definition_nodes[sid]=node
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            symbols.append(Symbol(sid, path, node.name, qualified, kind, start, node.end_lineno,
                                  "".join(lines[start - 1:node.end_lineno]),
                                  kind in {"function", "async_function"} and node.name.startswith("test_") and
                                  (not self.scope or len(self.scope) == 1 and self.scope[0].startswith("Test")) and
                                  (Path(path).name.startswith("test_") or Path(path).name.endswith("_test.py"))))
            previous = self.owner
            self.owner = sid
            self.scope.append(node.name)
            for child in node.body:
                self.visit(child)
            self.scope.pop()
            self.owner = previous

        def visit_FunctionDef(self, node):
            self.definition(node, "function")

        def visit_AsyncFunctionDef(self, node):
            self.definition(node, "async_function")

        def visit_ClassDef(self, node):
            self.definition(node, "class")

        def visit_Call(self, node):
            if self.owner:
                expression = ast.unparse(node.func)
                if self.anonymous:
                    expression = "<lambda/comprehension> " + expression
                calls.append((self.owner, expression, node.lineno))
            self.generic_visit(node)

        def visit_Lambda(self, node):
            self.anonymous += 1
            self.generic_visit(node)
            self.anonymous -= 1

        visit_ListComp = visit_Lambda
        visit_SetComp = visit_Lambda
        visit_DictComp = visit_Lambda
        visit_GeneratorExp = visit_Lambda

        def visit_Import(self, node):
            for alias in node.names:
                imports.append((self.owner, alias.asname or alias.name.split(".")[0],
                                alias.name if alias.asname else alias.name.split(".")[0], 0))

        def visit_ImportFrom(self, node):
            for alias in node.names:
                imports.append((self.owner, alias.asname or alias.name,
                                ".".join(filter(None, [node.module, alias.name])), node.level))

    Extractor().visit(tree)
    return symbols, calls, imports


def module_name(path: str) -> str:
    parts = list(Path(path).with_suffix("").parts)
    if parts and parts[0] == "src":
        parts.pop(0)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def index_repository(root: Path, cancel: Event | None = None, progress: Callable = lambda *_: None) -> Snapshot:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("Choose an existing repository folder")
    hashes = fingerprint(root, cancel)
    profile=project_profile(root,hashes); profile["config_paths"]=[path for path in hashes if is_config(path)]
    symbols, calls, imports, warnings = {}, [], {}, []
    sources = {}; units={}; definitions={}
    warnings.extend(profile["warnings"])
    for number, (path, digest) in enumerate(hashes.items()):
        checkpoint(cancel)
        progress(f"Parsing {number + 1}/{len(hashes)}: {path}")
        if digest in {"oversized", "unreadable"}:
            warnings.append(f"Skipped {path}: {digest}")
            continue
        try:
            raw = (root / path).read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError("File changed during indexing; reindex")
            source = decode_source(raw,path)
            if not is_source(path):continue
            if language_for(path)!="python":
                from .syntax import parse_unit
                unit=parse_unit(path,source); units[path]=unit; symbols.update((s.id,s) for s in unit.symbols)
                continue
            file_definitions={}
            found, file_calls, bindings = parse_file(path, source,file_definitions)
            definitions.update(file_definitions)
            sources[path] = source
            symbols.update((s.id, s) for s in found)
            calls.extend(file_calls)
            imports[path] = bindings
        except (SyntaxError, UnicodeError, OSError, ValueError, RecursionError) as exc:
            warnings.append(f"Cannot parse {path}: {exc}")
    # A fully qualified target must be unique. Ambiguity remains unresolved.
    qualified = {}
    for symbol in symbols.values():
        if language_for(symbol.path)!="python":continue
        qualified.setdefault(f"{module_name(symbol.path)}.{symbol.qualname}".strip("."), []).append(symbol.id)
    def absolute_import(path, target, level):
        if not level:
            return target
        package = module_name(path).split(".")
        if Path(path).name != "__init__.py":
            package = package[:-1]
        package = package[:max(0, len(package) - level + 1)]
        return ".".join(package + [target])

    exports = {}
    for path, bindings in imports.items():
        for owner, alias, target, level in bindings:
            if owner is None and alias != "*":
                exports[f"{module_name(path)}.{alias}".strip(".")] = absolute_import(path, target, level)

    def resolve(name):
        visited = set()
        while name not in visited:
            visited.add(name)
            if name in qualified:
                return qualified[name]
            parts = name.split(".")
            for size in range(len(parts), 0, -1):
                prefix = ".".join(parts[:size])
                if prefix in exports:
                    name = ".".join([exports[prefix]] + parts[size:])
                    break
            else:
                break
        return []

    from .scopes import ScopedCalls
    scoped = ScopedCalls(symbols, imports, sources, resolve, absolute_import, module_name)
    # Reuse the full-file AST: dedenting a fragment changes multiline-string
    # indentation and can reject otherwise valid methods/classes.
    function_nodes={sid:node for sid,node in definitions.items() if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}
    edges = []
    for caller, expression, line in calls:
        checkpoint(cancel)
        owner = symbols[caller]
        candidates = []
        relationship = "static_reference"
        parent = owner.qualname.rsplit(".", 1)[0] if "." in owner.qualname else ""
        # Receiver types are inferred from the enclosing class, not proven at runtime.
        if expression.startswith(("self.", "cls.")) and parent and scoped.unmodified_receiver(caller, expression.split(".")[0]):
            class_symbol = symbols.get(f"{owner.path}:{parent}")
            if class_symbol and class_symbol.kind == "class":
                candidates.extend(resolve(f"{module_name(owner.path)}.{parent}.{expression.split('.', 1)[1]}"))
                relationship = "inferred_method"
        candidates.extend(scoped.candidates(caller, expression))
        candidates = sorted(set(candidates))
        if len(candidates) == 1:
            edges.append({"caller": caller, "callee": candidates[0], "line": line,
                          "expression": expression, "kind": relationship})
        else:
            warnings.append(f"Unresolved call {owner.path}:{line}: {expression} (dynamic, external, shadowed or ambiguous)")
    for symbol in symbols.values():
        if language_for(symbol.path)!="python":continue
        if "." not in symbol.qualname:
            continue
        parent_id = f"{symbol.path}:{symbol.qualname.rsplit('.', 1)[0]}"
        parent = symbols.get(parent_id)
        if parent and parent.kind in {"function", "async_function"}:
            edges.append({"caller": parent_id, "callee": symbol.id, "line": symbol.start,
                          "expression": f"defines nested {symbol.name}", "kind": "enclosing_scope"})
    from .fixtures import fixture_edges
    fixture_links, fixture_warnings = fixture_edges({sid:s for sid,s in symbols.items() if language_for(s.path)=="python"}, function_nodes, imports, sources,
        resolve, absolute_import, checkpoint, cancel,{sid:node for sid,node in definitions.items() if isinstance(node,ast.ClassDef)})
    edges.extend(fixture_links)
    warnings.extend(fixture_warnings)
    if units:
        from .polyglot import link_units
        extra_edges,extra_warnings=link_units(root,units,profile,cancel)
        edges.extend(extra_edges); warnings.extend(extra_warnings)
    rev = revision(root)
    sid = hashlib.sha256(json.dumps([str(root), rev, hashes], sort_keys=True).encode()).hexdigest()[:20]
    return Snapshot(str(root), rev, hashes, symbols, edges, warnings, sid,profile)


def ensure_fresh(snapshot: Snapshot):
    root = Path(snapshot.root)
    if revision(root) != snapshot.revision or fingerprint(root) != snapshot.hashes:
        raise ValueError("Repository changed since indexing. Reindex before generating a patch.")


def save_snapshot(snapshot: Snapshot):
    with sqlite3.connect(app_dir() / "cache.sqlite3") as db:
        db.execute("CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, root TEXT, payload TEXT)")
        # Retain the most recent index per repository, not an unbounded history.
        db.execute("DELETE FROM snapshots WHERE root = ?", (snapshot.root,))
        db.execute("INSERT INTO snapshots VALUES (?, ?, ?)", (snapshot.id, snapshot.root, json.dumps(asdict(snapshot))))


def changed_symbols(snapshot: Snapshot, cancel: Event | None = None) -> dict:
    root = Path(snapshot.root)
    if snapshot.revision == "no-head":
        return {"files": [], "seeds": [], "historical_symbols": {}, "historical_edges": [],
                "warnings": ["No Git HEAD. Select a function to analyze its potential impact."]}
    files, seeds, historical, historical_edges, warnings = [], set(), {}, [], []
    old_sources={}
    prefix = git(root, "rev-parse", "--show-prefix").strip()
    names = [path for path in git(root, "diff", "--relative", "--no-ext-diff", "--no-textconv", "--name-only", "--no-renames", "-z", "HEAD", "--").split("\0") if is_indexable(path)]
    untracked = [path for path in git(root, "ls-files", "--others", "--exclude-standard", "-z", "--").split("\0") if is_indexable(path)]
    for path in filter(None, names + untracked):
        checkpoint(cancel)
        if any(p in EXCLUDED for p in Path(path).parts):
            continue
        try:
            old = git(root, "show", f"HEAD:{prefix}{path}") if path not in untracked else ""
        except ValueError:
            old = ""
        old_sources[path]=old
        current = ""
        if path in snapshot.hashes and snapshot.hashes[path] not in {"oversized", "unreadable"}:
            current = decode_source((root / path).read_bytes(),path)
        status = "untracked addition" if path in untracked else ("deleted" if not (root / path).exists() else "modified" if old else "added")
        files.append({"path": path, "status": status,"before":old,"after":current,
                      "diff": "".join(difflib.unified_diff(old.splitlines(True), current.splitlines(True),
                                                           fromfile="a/" + path, tofile="b/" + path))})
        if is_config(path):
            seeds.update(configuration_seeds(snapshot,path)); warnings.append(f"Configuration edit in {path}: included related source conservatively."); continue
        try:
            old_symbols, _, _ = parse_file(path, old)
        except SyntaxError:
            old_symbols = []
            warnings.append(f"Historical parse failed: {path}")
        old_map = {s.id: s for s in old_symbols}
        new_map = {sid: s for sid, s in snapshot.symbols.items() if s.path == path}
        # Whole-symbol text comparison includes deleted functions and decorators.
        for sid in old_map.keys() | new_map.keys():
            if sid not in old_map or sid not in new_map or symbol_changed(old_map[sid],new_map[sid]):
                seeds.add(sid)
                if sid not in new_map:
                    historical[sid] = asdict(old_map[sid])
        def module_statements(source):
            try:
                return [ast.dump(node) for node in ast.parse(source).body
                        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
            except SyntaxError:
                return None
        if language_for(path)=="python" and module_statements(old) != module_statements(current):
            # Constants, imports and configuration can affect every unit in a file.
            # Expose this conservative expansion instead of returning an empty result.
            seeds.update(new_map)
            warnings.append(f"Module-level change in {path}: conservatively included all its symbols.")
    # Resolve surviving callers to removed functions using historical identities.
    if historical:
        all_symbols = {**snapshot.symbols, **{sid: Symbol(**value) for sid, value in historical.items()}}
        names_by_module = {}
        for sid, s in all_symbols.items():
            names_by_module.setdefault(f"{module_name(s.path)}.{s.qualname}", []).append(sid)
        for s in snapshot.symbols.values():
            if language_for(s.path)!="python":continue
            try:
                _, calls, bindings = parse_file(s.path, decode_source((root / s.path).read_bytes()))
            except (SyntaxError, OSError, UnicodeError):
                continue
            for caller, expression, line in calls:
                if caller != s.id:
                    continue
                targets = [f"{module_name(s.path)}.{expression}"]
                for owner, alias, target, level in bindings:
                    if not level and owner in (None, caller) and (expression == alias or expression.startswith(alias + ".")):
                        targets.append(target + expression[len(alias):])
                for target in targets:
                    matches = names_by_module.get(target, [])
                    if len(matches) == 1 and matches[0] in historical:
                        historical_edges.append({"caller": caller, "callee": matches[0], "line": line,
                                                 "expression": expression, "kind": "historical_reference"})
        if any(language_for(value["path"])!="python" for value in historical.values()):
            from .polyglot import historical_links
            historical_edges.extend(historical_links(snapshot,old_sources,historical,cancel))
    return {"files": files, "seeds": sorted(seeds), "historical_symbols": historical,
            "historical_edges": historical_edges, "warnings": warnings}


def symbol_changed(before,after):
    return (before.change_key or before.source)!=(after.change_key or after.source)


def configuration_seeds(snapshot,path):
    prefix=Path(path).parent.as_posix()
    values=[s for s in snapshot.symbols.values() if prefix=="." or s.path.startswith(prefix+"/")]
    return [s.id for s in values if s.kind=="module" or language_for(s.path)=="python"]


def impact_paths(snapshot: Snapshot, seeds: list[str], extra_edges: list[dict] | None = None, cancel=None) -> list[dict]:
    reverse = {}
    for edge in snapshot.edges + (extra_edges or []):
        checkpoint(cancel)
        reverse.setdefault(edge["callee"], []).append(edge)
    found, queue = {}, deque((seed, [seed], []) for seed in sorted(set(seeds)))
    while queue:
        checkpoint(cancel)
        node, path, evidence = queue.popleft()
        if node in found:
            continue
        found[node] = {"symbol": node, "distance": len(path) - 1, "path": path,
                       "evidence": evidence, "status": "potential impact"}
        for edge in reverse.get(node, []):
            queue.append((edge["caller"], path + [edge["caller"]], evidence + [edge]))
    return list(found.values())


def test_link_gaps(snapshot: Snapshot, seeds: list[str], cancel=None) -> list[str]:
    """Find seeds unreachable from any test in one traversal, instead of one per seed."""
    forward = {}
    for edge in snapshot.edges:
        checkpoint(cancel)
        forward.setdefault(edge["caller"], []).append(edge["callee"])
    seen, queue = set(), deque(s.id for s in snapshot.symbols.values() if s.is_test)
    while queue:
        checkpoint(cancel)
        sid = queue.popleft()
        if sid not in seen:
            seen.add(sid)
            queue.extend(forward.get(sid, []))
    return [sid for sid in seeds if sid not in seen]


def rename_local(snapshot: Snapshot, sid: str, old: str, new: str) -> dict:
    ensure_fresh(snapshot)
    if old == new or not old.isidentifier() or not new.isidentifier() or keyword.iskeyword(new):
        raise ValueError("Use two different valid Python identifiers")
    symbol = snapshot.symbols[sid]
    if language_for(symbol.path)!="python":raise ValueError("Reviewed local-variable rename currently supports Python only.")
    path = Path(snapshot.root) / symbol.path
    raw = path.read_bytes()
    source = decode_source(raw)
    tree = ast.parse(source)
    fn = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == symbol.name
               and n.end_lineno == symbol.end), None)
    if fn is None or symbol.kind != "function" or "." in symbol.qualname:
        raise ValueError("Only top-level ordinary functions are supported in this prototype")
    args = {n.arg for n in ast.walk(fn.args) if isinstance(n, ast.arg)}
    if old in args or new in args:
        raise ValueError("Parameter names cannot be renamed or shadowed")
    forbidden = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda, ast.ListComp,
                 ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.Global, ast.Nonlocal,
                 ast.Import, ast.ImportFrom, ast.JoinedStr, ast.Match)
    # Defaults, annotations and decorators execute outside the function's local
    # scope. Never rewrite their names when renaming a body-local assignment.
    nodes = [fn] + [node for statement in fn.body for node in ast.walk(statement)]
    if any(isinstance(n, forbidden) for n in nodes[1:]):
        raise ValueError("Nested scopes, comprehensions, imports, pattern matching and f-strings are unsupported")
    if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in
           {"locals", "globals", "vars", "eval", "exec", "compile", "__import__"} for n in nodes):
        raise ValueError("Dynamic namespace access is unsupported")
    if any(isinstance(n, ast.ExceptHandler) and n.name in {old, new} for n in nodes):
        raise ValueError("Exception-handler bindings are unsupported")
    names = [n for n in nodes if isinstance(n, ast.Name)]
    if any(n.id == new for n in names) or new == fn.name:
        raise ValueError("New name collides with an existing name")
    if not any(n.id == old and isinstance(n.ctx, ast.Store) for n in names):
        raise ValueError("Old name must be a local assignment target")
    lines = source.splitlines(keepends=True)
    positions = set()
    for node in names:
        if node.id == old:
            # AST uses UTF-8 byte columns; tokenize uses character columns.
            line = lines[node.lineno - 1]
            column = len(line.encode("utf-8")[:node.col_offset].decode("utf-8"))
            positions.add((node.lineno, column))
    replacements = {}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.NAME and token.string == old and token.start in positions:
            replacements.setdefault(token.start[0], []).append((token.start[1], token.end[1]))
    if sum(map(len, replacements.values())) != len(positions):
        raise ValueError("Cannot preserve all token boundaries; rename rejected")
    for row, spans in replacements.items():
        for start, end in sorted(spans, reverse=True):
            lines[row - 1] = lines[row - 1][:start] + new + lines[row - 1][end:]
    proposed = "".join(lines)
    ast.parse(proposed)
    return {"snapshot": snapshot.id, "path": symbol.path, "symbol": sid, "old": old, "new": new,
            "diff": "".join(difflib.unified_diff(source.splitlines(True), proposed.splitlines(True),
                                                fromfile="a/" + symbol.path, tofile="b/" + symbol.path)),
            "proposed_source": proposed, "syntax_validation": "passed", "tests": "not run",
            "limitations": "Static scope checks do not prove behavior preservation."}


def report_markdown(report: dict) -> str:
    lines = ["# Change Lens analysis", "", f"Snapshot: {report['snapshot']}", "",
             "Potential impact inferred from static references; not proof of runtime behavior.", "",
             f"Freshness: {report.get('freshness', 'Snapshot report; compare hashes before relying on current source.')}", "",
             "## Language capabilities", ""]
    for name,capability in report.get("profile",{}).get("capabilities",{}).items():
        lines.append(f"- {capability['language']}: {capability['impact']}; test execution: {capability['test_execution']}")
    for item in report.get("profile",{}).get("frameworks",[]):
        lines.append(f"- {item['name']} detected in {item['path']}: {item['evidence']}. {item['note']}")
    lines += ["", "## Affected code", ""]
    for item in report.get("impact", []):
        lines.append("- " + " → ".join(item["path"]))
        for edge in item.get("evidence", []):
            lines.append(f"  - {edge['caller']} → {edge['callee']} at line {edge['line']} ({edge['kind']}: {edge['expression']})")
    if report.get('relationships'):
        lines += ['', '## Recorded relationships (including alternate routes)', '']
        lines += [f"- {edge['caller']} → {edge['callee']} at line {edge['line']} ({edge['kind']})" for edge in report['relationships']]
    lines += ['', '## Recommended tests', '']
    if report.get("ranking"):
        lines += [report["ranking"]["method"], report["ranking"]["policy"], ""]
    for item in report.get("tests", []):
        if item.get("recommended", True):
            lines.append(f"- {item['symbol']} — ranking score {item['score']:.4f}; {item['method']}; {item.get('relation','')}")
            if item.get("reason"):lines.append("  - " + item["reason"])
    optional = [item for item in report.get("tests", []) if not item.get("recommended", True)]
    if optional:
        lines += ["", "## Other candidates (not recommended by dependency evidence)", ""]
        lines += [f"- {item['symbol']} — {item.get('relation','unlinked')}; {item.get('reason','')}" for item in optional]
    if report.get("possible_gaps"):
        lines += ["", "## Possible test linkage gaps", "", "No static link was found; tests may still exist.", ""]
        lines += ["- " + sid for sid in report["possible_gaps"]]
    if report.get("demo_validation"):
        validation = report["demo_validation"]
        lines += ["", "## Demo validation", "", f"Selected tests: {validation['selected']['status']}",
                  f"Full suite: {validation['full']['status']}",
                  f"Controlled mutation: {validation['controlled_mutation']}",
                  f"Observed failing-test recall: {validation['failing_test_recall']}",
                  "Passing tests do not prove behavior preservation."]
    if report.get("test_run"):
        run = report["test_run"]
        lines += ["", "## Executed selected tests", "", f"Status: {run['status']}",
                  f"Exit code: {run['returncode']}; requested {run.get('selection_unit','tests')}: {run['tests_requested']}; elapsed: {run['seconds']:.2f}s",
                  run.get('scope','selected tests'),
                  "Saved source was executed; preview patches were not applied. The complete project suite was not run."]
    elif not report.get("demo_validation"):
        lines += ["", "## Checks not performed", "", "Tests were not executed. Static analysis does not prove behavior preservation."]
    lines += ["", "## Warnings", ""] + ["- " + w for w in report.get("warnings", [])]
    return "\n".join(lines) + "\n"
