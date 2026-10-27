"""Offline refactoring previews. Rope changes are inspected, never executed."""
import ast
import difflib
import keyword
from pathlib import Path
import hashlib
import json
import uuid

from .core import EXCLUDED, checkpoint, decode_source, ensure_fresh
from .languages import language_for


def preview_refactoring(snapshot, path: str, operation: str, new_name: str, offset: int, end: int | None = None,
                        cancel=None, progress=lambda *_: None):
    if language_for(path)!="python":raise ValueError("Reviewed rename/extract refactoring currently supports Python only. Other languages support analysis and local AI completion/briefs.")
    from rope.base.project import Project
    from rope.base.taskhandle import TaskHandle
    from rope.base.change import ChangeContents, ChangeSet
    from rope.refactor.rename import Rename
    from rope.refactor.extract import ExtractMethod, ExtractVariable
    ensure_fresh(snapshot)
    if not new_name.isidentifier() or keyword.iskeyword(new_name):
        raise ValueError("Enter a valid Python identifier for the new name.")
    root = Path(snapshot.root)
    target = (root / path).resolve()
    if not target.is_relative_to(root) or path not in snapshot.hashes or target.is_symlink():
        raise ValueError("Choose an indexed Python file inside this workspace.")
    source = decode_source(target.read_bytes()).replace("\r\n", "\n")
    if not 0 <= offset < len(source):
        raise ValueError("Place the cursor on a name, or select a block of code first.")

    class Handle(TaskHandle):
        def is_stopped(self):
            return cancel is not None and cancel.is_set()

    handle = Handle("Refactoring preview")
    handle.add_observer(lambda: progress("Finding related references…"))
    # No .ropeproject/config.py is read; dynamic object execution is disabled.
    project = Project(str(root), ropefolder=None, project_opened=None, perform_doa=False,
                      automatic_soa=False, extension_modules=[], import_dynload_stdmods=False,
                      ignored_resources=list(EXCLUDED), save_objectdb=False)
    try:
        resource = project.get_file(path)
        checkpoint(cancel)
        if operation == "rename":
            refactor = Rename(project, resource, offset)
            old_name = refactor.get_old_name()
            # Avoid the most common accidental shadowing/collision before Rope resolves references.
            scope = project.get_pymodule(resource).get_scope().get_inner_scope_for_line(source[:offset].count("\n") + 1)
            if new_name != old_name and new_name in scope.get_names():
                raise ValueError(f"'{new_name}' is already defined in this scope.")
            if new_name == old_name:
                raise ValueError("Choose a different name.")
            changes = refactor.get_changes(new_name, docs=False, task_handle=handle)
        else:
            if end is None or end <= offset or end > len(source):
                raise ValueError("Select an expression or a complete block of statements in the editor.")
            scope = project.get_pymodule(resource).get_scope().get_inner_scope_for_line(source[:offset].count("\n") + 1)
            while scope is not None:
                if new_name in scope.get_names():
                    raise ValueError(f"'{new_name}' is already defined in this scope or an enclosing scope. Choose an unused name.")
                scope = scope.parent
            old_name = "selection"
            if operation == "extract_method":
                changes = ExtractMethod(project, resource, offset, end).get_changes(new_name)
            elif operation == "extract_variable":
                changes = ExtractVariable(project, resource, offset, end).get_changes(new_name)
            else:
                raise ValueError("Unknown refactoring operation")
        checkpoint(cancel)
        files = []

        def collect(change):
            if isinstance(change, ChangeSet):
                for child in change.changes:
                    collect(child)
            elif isinstance(change, ChangeContents):
                relative = change.resource.path
                original = decode_source((root / relative).read_bytes()).replace("\r\n", "\n")
                proposed = change.new_contents
                ast.parse(proposed, filename=relative)
                files.append({"path": relative, "before": original, "after": proposed,
                              "diff": "".join(difflib.unified_diff(original.splitlines(True), proposed.splitlines(True),
                                                                   fromfile="a/"+relative, tofile="b/"+relative))})
            else:
                raise ValueError("This preview requires an unsupported file operation; nothing was modified.")
        collect(changes)
        if not files:
            raise ValueError("No supported references were found at this position.")
        files.sort(key=lambda row: (row["path"] != path, row["path"]))
        return {"snapshot": snapshot.id, "path": path, "operation": operation, "old": old_name,
                "new": new_name, "files": files, "diff": "".join(row["diff"] for row in files),
                "syntax_validation": "passed", "tests": "not run",
                "limitations": "Preview only. Dynamic references can be missed. Review each file and run your tests before applying."}
    finally:
        project.close()


def suggestions(symbol):
    from .python_source import symbol_node
    if language_for(symbol.path)!='python':return []
    try:
        tree = symbol_node(symbol)
    except SyntaxError:
        return []
    decisions = sum(isinstance(node, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.IfExp)) for node in ast.walk(tree))
    count = len(symbol.source.splitlines())
    rows = []
    if count >= 30 or decisions >= 6:
        rows.append({"title": "Extract a focused helper", "reason": f"{count} lines and {decisions} branching statements. Select a cohesive block, then preview Extract helper.", "operation": "extract_method"})
    if any(isinstance(n, ast.BinOp) and any(isinstance(child, ast.BinOp) for child in ast.iter_child_nodes(n)) for n in ast.walk(tree)):
        rows.append({"title": "Name a complex expression", "reason": "An expression combines multiple operations. Select it and preview Extract variable.", "operation": "extract_variable"})
    rows.append({"title": "Rename with reference updates", "reason": "Place the cursor on a name. Preview its related usages across Python files before exporting the patch.", "operation": "rename"})
    return rows


def apply_reviewed_patch(snapshot, patch):
    """Apply an explicitly reviewed preview with conflict checks and recoverable backups."""
    from .core import app_dir
    from .workspace import Document, capture_baseline, load_baseline
    ensure_fresh(snapshot)
    if patch.get("snapshot") != snapshot.id:
        raise ValueError("This patch belongs to a different snapshot. Generate a fresh preview.")
    root = Path(snapshot.root)
    prepared = []
    for row in patch["files"]:
        if language_for(row["path"])!="python" and patch.get('operation')!='ai_rewrite':raise ValueError("Structural rename/extract currently supports Python only.")
        path = (root / row["path"]).resolve()
        if not path.is_relative_to(root) or row["path"] not in snapshot.hashes or path.is_symlink():
            raise ValueError("Patch path is outside the indexed workspace.")
        document = Document(path)
        if document.text != row["before"]:
            raise ValueError(f"{row['path']} changed after this preview. Nothing was applied.")
        if language_for(row['path'])=='python':ast.parse(row['after'],filename=row['path'])
        else:
            from .syntax import parse_unit
            parse_unit(row['path'],row['after'])
        prepared.append((row, document))
    if not prepared:
        raise ValueError("No reviewed file changes to apply.")
    if snapshot.revision == "no-head" and load_baseline(snapshot.root) is None:
        capture_baseline(snapshot)
    backup = app_dir() / "backups" / uuid.uuid4().hex
    backup.mkdir(parents=True)
    metadata = {"root": snapshot.root, "snapshot": snapshot.id, "files": []}
    for index, (row, document) in enumerate(prepared):
        (backup / f"{index}.original").write_bytes(document.raw)
        metadata["files"].append({"path": row["path"], "backup": f"{index}.original",
                                   "after_sha256": hashlib.sha256(row["after"].replace("\n",document.newline).encode(document.encoding)).hexdigest()})
    (backup / "manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    applied = []
    try:
        for row, document in prepared:
            document.save(row["after"])
            applied.append((row, document))
    except Exception:
        for row, document in reversed(applied):
            document.save(row["before"])
        raise
    return {"files": [row["path"] for row, _ in prepared], "backup": str(backup)}

