from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
from threading import Event

import pytest

from changelens.core import (Cancelled, changed_symbols, ensure_fresh, impact_paths, index_repository,
                            rename_local, save_snapshot, report_markdown)
from changelens.ranking import evaluate, rank_tests, resources, train_model
from changelens.demo import execute_demo, verify_demo


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def init_git(root):
    run_git(root, "init")
    run_git(root, "config", "user.email", "test@example.invalid")
    run_git(root, "config", "user.name", "Test")
    run_git(root, "add", ".")
    run_git(root, "commit", "-m", "fixture")


def test_alias_transitive_cycles_duplicates(tmp_path):
    write(tmp_path, "a.py", "def compute():\n    return 1\n")
    write(tmp_path, "b.py", "from a import compute as calculate\ndef service():\n    return calculate()\ndef route():\n    return service()\n")
    write(tmp_path, "other.py", "def compute():\n    return 2\n")
    write(tmp_path, "cycle.py", "def one():\n    return two()\ndef two():\n    return one()\n")
    snapshot = index_repository(tmp_path)
    paths = {r["symbol"]: r for r in impact_paths(snapshot, ["a.py:compute"])}
    assert paths["b.py:route"]["path"] == ["a.py:compute", "b.py:service", "b.py:route"]
    assert "other.py:compute" not in paths
    assert len(impact_paths(snapshot, ["cycle.py:one"])) == 2


def test_module_qualified_and_relative(tmp_path):
    write(tmp_path, "pkg/__init__.py", "")
    write(tmp_path, "pkg/a.py", "def compute():\n    return 1\n")
    write(tmp_path, "pkg/b.py", "from .a import compute as c\nimport pkg.a as a\ndef run():\n    return c() + a.compute()\n")
    snapshot = index_repository(tmp_path)
    assert sum(e["callee"] == "pkg/a.py:compute" for e in snapshot.edges) == 2


def test_unresolved_and_syntax_errors_no_execution(tmp_path):
    write(tmp_path, "broken.py", "def nope(\n")
    write(tmp_path, "dynamic.py", "raise RuntimeError('must never execute')\ndef run(callback):\n    return callback()\n")
    snapshot = index_repository(tmp_path)
    assert any("Cannot parse broken.py" in w for w in snapshot.warnings)
    assert any("callback" in w for w in snapshot.warnings)


def test_shadowed_names_and_reexports(tmp_path):
    write(tmp_path, "pkg/__init__.py", "from .impl import compute\n")
    write(tmp_path, "pkg/impl.py", "def compute():\n    return 1\n")
    write(tmp_path, "user.py", "import pkg\ndef run():\n    return pkg.compute()\ndef shadow(pkg):\n    return pkg.compute()\n")
    snapshot = index_repository(tmp_path)
    assert any(e["caller"] == "user.py:run" and e["callee"] == "pkg/impl.py:compute" for e in snapshot.edges)
    assert not any(e["caller"] == "user.py:shadow" for e in snapshot.edges)


def test_class_scope_is_not_function_lexical_scope(tmp_path):
    write(tmp_path, "a.py", "class A:\n    def foo(self):\n        return bar()\n    def bar(self):\n        return 1\n")
    snapshot = index_repository(tmp_path)
    assert not snapshot.edges


def test_exclusions_and_cancel(tmp_path):
    write(tmp_path, ".venv/secret.py", "def secret(): pass")
    write(tmp_path, "a.py", "def ok(): pass")
    assert set(index_repository(tmp_path).symbols) == {"a.py:ok"}
    cancel = Event()
    cancel.set()
    with pytest.raises(Cancelled):
        index_repository(tmp_path, cancel)


def test_unicode_paths_and_stale(tmp_path):
    folder = tmp_path / "परीक्षण space"
    folder.mkdir()
    write(folder, "café.py", "def hello():\n    return 1\n")
    snapshot = index_repository(folder)
    ensure_fresh(snapshot)
    write(folder, "new.py", "")
    with pytest.raises(ValueError, match="changed"):
        ensure_fresh(snapshot)


def test_git_staged_unstaged_added_deleted(tmp_path):
    write(tmp_path, "a.py", "def compute():\n    return 1\n")
    write(tmp_path, "removed.py", "def removed():\n    return 1\n")
    write(tmp_path, "caller.py", "from removed import removed\ndef caller():\n    return removed()\n")
    init_git(tmp_path)
    write(tmp_path, "a.py", "def compute():\n    return 2\n")
    run_git(tmp_path, "add", "a.py")
    (tmp_path / "removed.py").unlink()
    write(tmp_path, "new.py", "def added():\n    return 3\n")
    snapshot = index_repository(tmp_path)
    changes = changed_symbols(snapshot)
    assert set(changes["seeds"]) == {"a.py:compute", "removed.py:removed", "new.py:added"}
    assert any(f["status"] == "untracked addition" for f in changes["files"])
    impacted = impact_paths(snapshot, changes["seeds"], changes["historical_edges"])
    assert any(i["symbol"] == "caller.py:caller" for i in impacted)


def test_no_head_function_mode(tmp_path):
    write(tmp_path, "a.py", "def f(): pass")
    changes = changed_symbols(index_repository(tmp_path))
    assert changes["warnings"] and not changes["seeds"]


def test_git_subdirectory_selection(tmp_path):
    write(tmp_path, "pkg/a.py", "def f():\n    return 1\n")
    write(tmp_path, "other.py", "def untouched(): pass\n")
    init_git(tmp_path)
    write(tmp_path, "pkg/a.py", "def f():\n    return 2\n")
    change = changed_symbols(index_repository(tmp_path / "pkg"))
    assert change["seeds"] == ["a.py:f"]
    assert [{"path":row["path"],"status":row["status"]} for row in change["files"]] == [{"path": "a.py", "status": "modified"}]


def test_cancellation_between_files(tmp_path):
    write(tmp_path, "a.py", "def f(): pass\n")
    write(tmp_path, "b.py", "def g(): pass\n")
    cancel = Event()
    with pytest.raises(Cancelled):
        index_repository(tmp_path, cancel, lambda message: cancel.set())


def test_rename_preserves_text_and_unicode(tmp_path):
    source = 'def calculate():\n    café = 1; subtotal = café + 2  # subtotal stays\n    text = "subtotal"\n    return subtotal, text\n\ndef other():\n    subtotal = 4\n    return subtotal\n'
    write(tmp_path, "a.py", source)
    patch = rename_local(index_repository(tmp_path), "a.py:calculate", "subtotal", "net")
    assert "net = café + 2  # subtotal stays" in patch["proposed_source"]
    assert '"subtotal"' in patch["proposed_source"]
    assert "subtotal = 4" in patch["proposed_source"]
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == source
    assert patch["syntax_validation"] == "passed"


def test_rename_does_not_rewrite_defaults_or_decorators(tmp_path):
    source = "subtotal = 8\n@decorate(subtotal)\ndef f(value=subtotal):\n    subtotal = value\n    return subtotal\n"
    write(tmp_path, "a.py", source)
    patch = rename_local(index_repository(tmp_path), "a.py:f", "subtotal", "net")
    assert "@decorate(subtotal)" in patch["proposed_source"]
    assert "value=subtotal" in patch["proposed_source"]
    assert "net = value" in patch["proposed_source"]


@pytest.mark.parametrize("body,old,new", [
    ("def f(x):\n    return x\n", "x", "y"),
    ("def f():\n    x = 1\n    y = 2\n    return x+y\n", "x", "y"),
    ("def f():\n    x = 1\n    def inner(): return x\n    return inner()\n", "x", "y"),
    ("def f():\n    x = [a for a in range(3)]\n    return x\n", "x", "y"),
    ("def f():\n    global x\n    x = 1\n", "x", "y"),
    ("def f():\n    x = 1\n    return locals()\n", "x", "y"),
    ("def f():\n    x = 1\n    return f'{x}'\n", "x", "y"),
    ("def f():\n    x = 1\n    return x\n", "x", "class"),
    ("def f():\n    try: x = 1\n    except Exception as e: pass\n    return x\n", "x", "e"),
])
def test_rejected_renames(tmp_path, body, old, new):
    write(tmp_path, "a.py", body)
    with pytest.raises(ValueError):
        rename_local(index_repository(tmp_path), "a.py:f", old, new)


def test_rename_stale_rejected(tmp_path):
    write(tmp_path, "a.py", "def f():\n    x=1\n    return x\n")
    snapshot = index_repository(tmp_path)
    write(tmp_path, "a.py", "def f():\n    x=2\n    return x\n")
    with pytest.raises(ValueError):
        rename_local(snapshot, "a.py:f", "x", "y")


def test_training_reproducibility_and_fallback(tmp_path):
    first, second = tmp_path / "one.json", tmp_path / "two.json"
    assert train_model(first) == train_model(second)
    snapshot = index_repository(resources() / "demo")
    rows = rank_tests(snapshot, ["invoice.py:calculate_invoice_total"], model_path=first)
    assert len(rows) == 7 and rows[0]["method"] == "learned logistic regression"
    fallback = rank_tests(snapshot, ["invoice.py:calculate_invoice_total"], model_path=tmp_path / "missing")
    assert fallback[0]["method"] == "structural fallback"
    assert fallback[0]["distance"] == 1


def test_evaluation_reports_unsupported(tmp_path):
    snapshot = index_repository(resources() / "demo")
    cases = [{"id": "missing", "seeds": ["no.py:missing"], "relevant_tests": ["missing"]}]
    result = evaluate(snapshot, cases)
    assert all(r["supported"] == 0 and r["unsupported"] == 1 and r["recall_at_5"] is None for r in result["results"])


def test_cache_and_export(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    snapshot = index_repository(resources() / "demo")
    save_snapshot(snapshot)
    assert (tmp_path / "ChangeLens/cache.sqlite3").exists()
    assert "Snapshot: abc" in report_markdown({"snapshot": "abc"})


def test_demo_external_execution_rejected(tmp_path):
    with pytest.raises(ValueError, match="bundled"):
        verify_demo(tmp_path)


def test_demo_validation_and_fault_recall():
    snapshot = index_repository(resources() / "demo")
    selected = [r["symbol"].replace(":", "::", 1) for r in rank_tests(snapshot, ["invoice.py:calculate_invoice_total"])[:5]]
    normal = execute_demo(resources() / "demo", selected)
    assert normal["selected"]["returncode"] == normal["full"]["returncode"] == 0
    fault = execute_demo(resources() / "demo", selected, mutation=True)
    assert fault["full"]["returncode"] == 1 and fault["failing_test_recall"] == 1

