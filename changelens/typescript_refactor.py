"""Preview JS and TS edits with the pinned, offline TypeScript language service."""
import difflib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from .core import checkpoint, decode_source, ensure_fresh
from .languages import TYPESCRIPT_LANGUAGES, language_for
from .ranking import resources
from .syntax import parse_unit


def preview_typescript(snapshot, path, operation, new_name, offset, end, cancel, progress):
    ensure_fresh(snapshot)
    assets = resources() / "refactoring"
    if not (assets / "node_modules/typescript/lib/typescript.js").is_file():
        raise ValueError("The TypeScript refactoring engine is missing. Run scripts/setup.ps1 once to prepare it.")
    bundled = resources() / "formatting/node.exe"
    node = str(bundled) if bundled.is_file() else shutil.which("node")
    if not node:
        raise ValueError("Node.js is required for JavaScript and TypeScript refactoring. Run scripts/setup.ps1.")
    root = Path(snapshot.root)
    files = {}
    total_bytes = 0
    for relative, digest in snapshot.hashes.items():
        checkpoint(cancel)
        if language_for(relative) not in TYPESCRIPT_LANGUAGES or digest in {"oversized", "unreadable"}:
            continue
        target = root / relative
        if target.resolve() != target:
            continue
        raw = target.read_bytes()
        total_bytes += len(raw)
        if total_bytes > 32_000_000:
            raise ValueError("This workspace is too large for one refactor preview. Open the relevant package folder.")
        files[relative] = decode_source(raw, relative).replace("\r\n", "\n")
    if path not in files:
        raise ValueError("Choose a JavaScript or TypeScript file indexed in this project.")
    source = files[path]
    if not 0 <= offset < len(source):
        raise ValueError("Click a name or select the code you want to extract.")
    if operation != "rename" and (end is None or not offset < end <= len(source)):
        raise ValueError("Select the code you want to extract in the editor.")
    payload = json.dumps({
        "root": str(root), "path": path, "files": files, "operation": operation, "newName": new_name,
        "start": len(source[:offset].encode("utf-16-le")) // 2,
        "end": len(source[:end].encode("utf-16-le")) // 2 if end is not None else None,
    }).encode()
    progress("Preparing JavaScript and TypeScript edits…")
    environment = {key: value for key, value in os.environ.items()
                   if key.upper() not in {"NODE_OPTIONS", "NODE_PATH", "QT_PLUGIN_PATH", "QML2_IMPORT_PATH"}}
    frozen_windows = os.name == "nt" and getattr(sys, "frozen", False)
    if frozen_windows:
        import ctypes
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    try:
        process = subprocess.Popen([node, "--no-addons", str(assets / "worker.cjs")], cwd=assets,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=environment, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    finally:
        if frozen_windows:
            ctypes.windll.kernel32.SetDllDirectoryW(sys._MEIPASS)
    started = time.monotonic()
    try:
        while True:
            checkpoint(cancel)
            if time.monotonic() - started > 30:
                raise ValueError("The TypeScript refactoring preview timed out.")
            try:
                output, error = process.communicate(payload, timeout=.1)
                break
            except subprocess.TimeoutExpired:
                payload = None
    except BaseException:
        process.kill()
        process.communicate()
        raise
    try:
        result = json.loads(output)
    except ValueError as exc:
        raise ValueError("The TypeScript refactoring engine could not start. "
                         + error.decode(errors="replace")[:300]) from exc
    if process.returncode:
        raise ValueError(result.get("error", "The TypeScript language service could not prepare this edit."))

    # Windows host paths can return different casing. Keep the indexed spelling for the patch.
    indexed = {os.path.normcase(name): name for name in files}
    changes = []
    for row in result["files"]:
        relative = indexed.get(os.path.normcase(row["path"]))
        if relative is None:
            raise ValueError("The preview included a file outside the indexed workspace.")
        before, after = files[relative], row["after"]
        try:
            parse_unit(relative, after)
        except SyntaxError as exc:
            raise ValueError(f"The proposed edit did not pass syntax validation in {relative}.") from exc
        diff = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                             fromfile="a/" + relative, tofile="b/" + relative))
        changes.append({"path": relative, "before": before, "after": after, "diff": diff})
    if not changes:
        raise ValueError("The selected refactor produced no changes.")
    ensure_fresh(snapshot)
    changes.sort(key=lambda row: (row["path"] != path, row["path"]))
    return {"snapshot": snapshot.id, "path": path, "operation": operation, "old": result["oldName"],
            "new": new_name, "files": changes, "diff": "".join(row["diff"] for row in changes),
            "syntax_validation": "passed", "tests": "not run",
            "limitations": "Preview prepared by the TypeScript language service. Review changes and run linked tests."}
