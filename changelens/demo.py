"""Run only manifest-verified bundled demo code in a disposable directory."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from .core import checkpoint
from .ranking import resources


def verify_demo(root: Path):
    canonical = (resources() / "demo").resolve()
    if root.resolve() != canonical:
        raise ValueError("Test execution is restricted to the bundled demo")
    manifest = json.loads((resources() / "demo_manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest.items():
        path = root / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Bundled demo integrity check failed")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    if actual != set(manifest):
        raise ValueError("Unexpected files in demo; test execution rejected")


def execute_demo(root: Path, selected: list[str], patch: dict | None = None, mutation=False,
                 cancel=None, progress=lambda *_: None) -> dict:
    verify_demo(root)
    # Only manifest-known node IDs can be supplied to the fixed pytest command.
    from .core import index_repository
    allowed = {s.id.replace(":", "::", 1) for s in index_repository(root).symbols.values() if s.is_test}
    if not selected or any(s not in allowed for s in selected):
        raise ValueError("Select at least one valid bundled demo test")
    with tempfile.TemporaryDirectory(prefix="ChangeLens-demo-") as folder:
        work = Path(folder)
        for name in json.loads((resources() / "demo_manifest.json").read_text(encoding="utf-8")):
            target = work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / name, target)
        if patch:
            if patch["path"] != "invoice.py":
                raise ValueError("Only invoice.py demo patches are supported")
            # Recreate the supported transformation rather than execute caller-supplied source.
            from .core import rename_local
            trusted = rename_local(index_repository(root), patch["symbol"], patch["old"], patch["new"])
            if trusted["diff"] != patch["diff"]:
                raise ValueError("Demo patch does not match the verified transformation")
            (work / "invoice.py").write_text(trusted["proposed_source"], encoding="utf-8")
        if mutation:
            target = work / "invoice.py"
            target.write_text(target.read_text(encoding="utf-8").replace("subtotal * (1 + tax_rate)", "subtotal * (1 - tax_rate)"), encoding="utf-8")
        results = {}
        for label, nodes in (("selected", selected), ("full", [])):
            checkpoint(cancel)
            progress(f"Running {label} demo tests")
            output = work / f"{label}.log"
            report_path = work / f"{label}.json"
            command = [sys.executable, "--demo-worker", str(work), str(report_path), *nodes] if getattr(sys, "frozen", False) else [sys.executable, "-I", str(resources() / "demo_worker.py"), str(work), str(report_path), *nodes]
            with output.open("w", encoding="utf-8") as stream:
                env = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONPATH": ""}
                process = subprocess.Popen(command, cwd=work, stdout=stream, stderr=subprocess.STDOUT, env=env,
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                started = time.monotonic()
                try:
                    while process.poll() is None:
                        checkpoint(cancel)
                        if time.monotonic() - started > 30:
                            raise TimeoutError("Demo tests exceeded the 30 second limit")
                        time.sleep(.05)
                except BaseException:
                    process.kill()
                    process.wait()
                    raise
            worker_log = Path(str(report_path) + ".stdout")
            results[label] = {"returncode": process.returncode, "output": (worker_log if worker_log.exists() else output).read_text(encoding="utf-8", errors="replace"),
                              "seconds": time.monotonic() - started,
                              "tests": json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else [],
                              "status": "passed" if process.returncode == 0 else "failed"}
        failed_full = {r["nodeid"] for r in results["full"]["tests"] if r["outcome"] == "failed"}
        failed_selected = {r["nodeid"] for r in results["selected"]["tests"] if r["outcome"] == "failed"}
        results["failing_test_recall"] = len(failed_selected & failed_full) / len(failed_full) if failed_full else None
        results["controlled_mutation"] = mutation
        results["limitations"] = "Bundled demo only. Passing tests do not prove behavior preservation. Temporary-directory execution is not an OS sandbox."
        return results

