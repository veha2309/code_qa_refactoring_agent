import ast
import json
from pathlib import Path
import sys

import pytest

from changelens.completion import complete_python, find_definition
from changelens.core import index_repository, impact_paths
from changelens.ranking import rank_tests, resources
from changelens.refactoring import apply_reviewed_patch, preview_refactoring
from changelens.runner import run_project_tests, test_node_id as node_id
from changelens.workspace import Document, analyze_workspace, capture_baseline


def write(root, path, source):
    target=root/path; target.parent.mkdir(parents=True,exist_ok=True); target.write_text(source,encoding="utf-8")


def test_completion_attributes_and_local_names(tmp_path):
    code="message = 'hello'\nmessage.up"
    values=complete_python(code,str(tmp_path/"a.py"),2,10,str(tmp_path))
    assert "upper" in {row["name"] for row in values}
    values=complete_python("invoice_total = 20\ninvoice_t",str(tmp_path/"a.py"),2,9,str(tmp_path))
    assert "invoice_total" in {row["name"] for row in values}


def test_completion_never_executes_python_modules(tmp_path):
    write(tmp_path,"unsafe.py",f"from pathlib import Path\nPath({str(tmp_path/'executed')!r}).write_text('bad')\ndef safe_name(): pass\n")
    values=complete_python("import unsafe\nunsafe.safe",str(tmp_path/"a.py"),2,11,str(tmp_path))
    assert "safe_name" in {row["name"] for row in values}
    assert not (tmp_path/"executed").exists()


def test_go_to_definition_follows_local_import(tmp_path):
    write(tmp_path,"a.py","def compute():\n    return 1\n")
    rows=find_definition("from a import compute\ncompute()",str(tmp_path/"b.py"),2,3,str(tmp_path))
    assert any(Path(row["path"])==tmp_path/"a.py" and row["line"]==1 for row in rows)


def test_document_save_preserves_crlf_and_rejects_conflicts(tmp_path):
    target=tmp_path/"a.py"; target.write_bytes(b"x = 1\r\n")
    doc=Document(target); doc.save("x = 2\n")
    assert target.read_bytes()==b"x = 2\r\n"
    target.write_text("x = 3\n")
    with pytest.raises(ValueError,match="outside"):doc.save("x = 4\n")


def test_baseline_changes_without_git_and_deletions(tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"cache"))
    write(tmp_path,"a.py","def total():\n    return 1\n")
    write(tmp_path,"test_a.py","from a import total\ndef test_total():\n    assert total() == 1\n")
    snapshot=index_repository(tmp_path); capture_baseline(snapshot)
    write(tmp_path,"a.py","def total():\n    return 2\n")
    indexed,report=analyze_workspace(tmp_path,comparison="baseline")
    assert report["changes"]["seeds"]==["a.py:total"]
    assert "return 1" in report["changes"]["files"][0]["before"]
    assert "return 2" in report["changes"]["files"][0]["after"]
    (tmp_path/"a.py").unlink()
    _,deleted=analyze_workspace(tmp_path,comparison="baseline")
    assert "test_a.py:test_total" in {row["symbol"] for row in deleted["impact"]}


def test_no_baseline_clear_error(tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"cache"))
    with pytest.raises(ValueError,match="Capture a baseline"):analyze_workspace(tmp_path,comparison="baseline")


def test_cursor_analysis_uses_fresh_ranges_and_rejects_module_scope(tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"cache"))
    write(tmp_path,"a.py","# module\n\ndef first(): return 1\n\ndef second(): return 2\n")
    _,report=analyze_workspace(tmp_path,seeds={"path":"a.py","line":5})
    assert report["changes"]["seeds"]==["a.py:second"]
    write(tmp_path,"a.py","# module\n\n\n\n\ndef first(): return 1\n\ndef second(): return 2\n")
    _,report=analyze_workspace(tmp_path,seeds={"path":"a.py","line":6})
    assert report["changes"]["seeds"]==["a.py:first"]
    with pytest.raises(ValueError,match="cursor inside"):
        analyze_workspace(tmp_path,seeds={"path":"a.py","line":1})


def test_non_git_constant_change_expands_functions(tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"cache"))
    write(tmp_path,"a.py","RATE = 1\ndef one(): return RATE\ndef two(): return RATE\n")
    capture_baseline(index_repository(tmp_path))
    write(tmp_path,"a.py","RATE = 2\ndef one(): return RATE + 1\ndef two(): return RATE\n")
    _,report=analyze_workspace(tmp_path,comparison="baseline")
    assert set(report["changes"]["seeds"])=={"a.py:one","a.py:two"}


def test_weak_tests_not_recommended():
    rows=rank_tests(index_repository(resources()/"demo"),["invoice.py:calculate_invoice_total"])
    recommended={r["symbol"] for r in rows if r["recommended"]}
    assert len(recommended)==5
    assert "test_invoice.py:test_shipping" not in recommended
    assert "test_invoice.py:test_discount" not in recommended
    assert all(row["reason"] for row in rows)


def test_nested_test_and_self_method_paths_are_labeled(tmp_path):
    write(tmp_path,"a.py","class Store:\n    def total(self): return 1\n    def route(self): return self.total()\n")
    write(tmp_path,"test_a.py","def test_nested():\n    def callback(): return 1\n    assert callback() == 1\n")
    snapshot=index_repository(tmp_path)
    assert any(e["kind"]=="inferred_method" and e["callee"]=="a.py:Store.total" for e in snapshot.edges)
    paths=impact_paths(snapshot,["test_a.py:test_nested.callback"])
    assert any(row["symbol"]=="test_a.py:test_nested" for row in paths)


def test_fixture_injection_and_nearest_override(tmp_path):
    write(tmp_path,"conftest.py","import pytest\n@pytest.fixture\ndef account(): return 1\n")
    write(tmp_path,"tests/conftest.py","import pytest\n@pytest.fixture\ndef account(): return 2\n@pytest.fixture\ndef service(account): return account\n")
    write(tmp_path,"tests/test_a.py","def test_service(service):\n    assert service == 2\n")
    snapshot=index_repository(tmp_path)
    paths=impact_paths(snapshot,["tests/conftest.py:account"])
    assert "tests/test_a.py:test_service" in {row["symbol"] for row in paths}
    assert not any(e["caller"]=="tests/conftest.py:service" and e["callee"]=="conftest.py:account" for e in snapshot.edges)
    result=rank_tests(snapshot,["tests/conftest.py:account"])[0]
    assert result["relation"]=="Fixture dependency"


def test_parametrized_argument_not_treated_as_fixture(tmp_path):
    write(tmp_path,"test_a.py","import pytest\n@pytest.fixture\ndef value(): return 1\n@pytest.mark.parametrize('value', [1, 2])\ndef test_value(value):\n    assert value\n")
    snapshot=index_repository(tmp_path)
    assert not any(e["kind"]=="fixture_dependency" for e in snapshot.edges)


def test_project_rename_preview_and_apply_with_backup(tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"cache"))
    source="def total(amount):\n    return amount + 1\n"
    write(tmp_path,"a.py",source); write(tmp_path,"b.py","from a import total\ndef route():\n    return total(1)\n")
    snapshot=index_repository(tmp_path)
    patch=preview_refactoring(snapshot,"a.py","rename","invoice_total",source.index("total"))
    assert {row["path"] for row in patch["files"]}=={"a.py","b.py"}
    assert (tmp_path/"a.py").read_text()==source
    result=apply_reviewed_patch(snapshot,patch)
    assert "invoice_total" in (tmp_path/"b.py").read_text()
    assert (Path(result["backup"])/"manifest.json").is_file()
    assert not (tmp_path/".ropeproject").exists()


def test_rope_does_not_run_project_config(tmp_path):
    write(tmp_path,".ropeproject/config.py",f"from pathlib import Path\nPath({str(tmp_path/'executed')!r}).write_text('bad')\n")
    source="def total(amount):\n    value = amount + 1\n    return value\n"
    write(tmp_path,"a.py",source)
    patch=preview_refactoring(index_repository(tmp_path),"a.py","rename","net",source.index("value"))
    assert "net" in patch["diff"] and not (tmp_path/"executed").exists()


@pytest.mark.parametrize("operation,selected,name",[("extract_method","    value = amount + 1\n    result = value * 2\n","compute_result"),("extract_variable","amount + 1","adjusted")])
def test_extract_previews(tmp_path,operation,selected,name):
    source="def total(amount):\n    value = amount + 1\n    result = value * 2\n    return result\n"
    write(tmp_path,"a.py",source); start=source.index(selected)
    patch=preview_refactoring(index_repository(tmp_path),"a.py",operation,name,start,start+len(selected))
    assert name in patch["diff"]
    ast.parse(patch["files"][0]["after"])
    assert (tmp_path/"a.py").read_text()==source


def test_apply_stale_patch_rejected(tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"cache"))
    source="def total(amount):\n    return amount\n"; write(tmp_path,"a.py",source)
    snapshot=index_repository(tmp_path); patch=preview_refactoring(snapshot,"a.py","rename","net",source.index("total"))
    write(tmp_path,"a.py",source+"# outside edit\n")
    with pytest.raises(ValueError):apply_reviewed_patch(snapshot,patch)


@pytest.mark.parametrize("operation,name,selection", [
    ("extract_variable", "amount", "amount + 1"),
    ("extract_variable", "existing", "amount + 1"),
    ("extract_method", "existing", "    value = amount + 1\n"),
])
def test_extraction_rejects_existing_names(tmp_path, operation, name, selection):
    source="def existing(): return 9\ndef total(amount):\n    value = amount + 1\n    return value\n"
    write(tmp_path,"a.py",source)
    start=source.index(selection)
    with pytest.raises(ValueError,match="already defined"):
        preview_refactoring(index_repository(tmp_path),"a.py",operation,name,start,start+len(selection))
    assert (tmp_path/"a.py").read_text()==source


def test_runner_requires_trust_and_preserves_test_class_node_ids(tmp_path):
    write(tmp_path,"test_a.py","class TestA:\n    def test_value(self):\n        assert True\n")
    snapshot=index_repository(tmp_path)
    assert node_id(snapshot,"test_a.py:TestA.test_value")=="test_a.py::TestA::test_value"
    with pytest.raises(ValueError,match="trusted"):run_project_tests(snapshot,["test_a.py:TestA.test_value"],sys.executable)
    result=run_project_tests(snapshot,["test_a.py:TestA.test_value"],sys.executable,trusted=True)
    assert result["returncode"]==0 and "1 passed" in result["output"]
