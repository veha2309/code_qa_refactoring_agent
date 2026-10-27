"""Explicitly trusted project test execution using the project's interpreter."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from .core import checkpoint, ensure_fresh
from .languages import language_for
from .js_runner import execution_family,javascript_command


def detect_interpreter(root: Path):
    for relative in (".venv/Scripts/python.exe", "venv/Scripts/python.exe", ".venv/bin/python", "venv/bin/python"):
        path = root / relative
        if path.is_file():
            return str(path)
    if not getattr(sys, "frozen", False):
        return sys.executable
    return shutil.which("python") or ""


def test_node_id(snapshot, sid):
    symbol = snapshot.symbols.get(sid)
    if not symbol or not symbol.is_test:
        raise ValueError("Choose tests discovered in the current workspace.")
    if language_for(symbol.path)!="python":raise ValueError("pytest node IDs are available for Python tests only.")
    return symbol.path + "::" + symbol.qualname.replace(".", "::")


def run_project_tests(snapshot, symbols, interpreter, trusted=False, timeout=120, cancel=None, progress=lambda *_: None):
    if not trusted:
        raise ValueError("This repository must be explicitly trusted before its tests can run.")
    ensure_fresh(snapshot)
    root = Path(snapshot.root)
    family=execution_family(snapshot,symbols)
    if family=="javascript":
        command,root,scope,requested=javascript_command(snapshot,symbols,interpreter);nodes=sorted({snapshot.symbols[sid].path for sid in symbols})
    elif family=='dart':
        from .flutter_sdk import flutter_command
        command,root,scope,requested=flutter_command(snapshot,symbols,interpreter);nodes=sorted({snapshot.symbols[sid].path for sid in symbols})
    elif family=="python":
        interpreter = str(Path(interpreter).resolve())
        if not Path(interpreter).is_file():raise ValueError("Choose a Python interpreter with this project's dependencies and pytest installed.")
        nodes = [test_node_id(snapshot, sid) for sid in symbols]
        command = [interpreter, "-m", "pytest", "-q", "--tb=short", *nodes]
        scope="selected tests in trusted Python repository";requested=len(nodes)
    else:raise ValueError("Select tests from one execution family: Python or JavaScript/TypeScript. Other languages currently provide structural recommendations only.")
    if not nodes:
        raise ValueError("Check at least one test to run.")
    checkpoint(cancel)
    started = time.monotonic()
    environment={key:value for key,value in os.environ.items() if key not in {'PYTHONPATH','PYTHONHOME','PYTEST_DISABLE_PLUGIN_AUTOLOAD','QT_PLUGIN_PATH','QML2_IMPORT_PATH'}}
    if family=='dart':
        from .flutter_sdk import sdk_environment
        environment.update(sdk_environment())
    with tempfile.TemporaryDirectory(prefix="ChangeLens-testlog-") as directory:
        log = Path(directory) / "output.log"
        with log.open("w", encoding="utf-8") as stream:
            frozen_windows = os.name == "nt" and getattr(sys, "frozen", False)
            if frozen_windows:
                import ctypes
                ctypes.windll.kernel32.SetDllDirectoryW(None)
            try:
                process = subprocess.Popen(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT,
                    env=environment,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), start_new_session=os.name != "nt")
            finally:
                if frozen_windows:
                    ctypes.windll.kernel32.SetDllDirectoryW(sys._MEIPASS)
            last = ""
            try:
                while process.poll() is None:
                    checkpoint(cancel)
                    if time.monotonic() - started > timeout:
                        raise TimeoutError(f"Test run exceeded {timeout} seconds.")
                    if log.stat().st_size > 2_000_000:
                        raise ValueError("Stopped test run after its output exceeded 2 MB.")
                    output = log.read_text(encoding="utf-8", errors="replace")
                    if output != last:
                        progress(output)
                        last = output
                    time.sleep(.1)
            except BaseException:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise
        output = log.read_text(encoding="utf-8", errors="replace")[:2_000_000]
    return {"returncode": process.returncode, "status": "passed" if process.returncode == 0 else "failed" if process.returncode == 1 else "could not complete",
            "output": output, "seconds": time.monotonic()-started, "command": command,
            "tests_requested": requested, "scope": scope,"selection_unit":"files/filters" if family in {'javascript','dart'} else "tests","language_family":family}
