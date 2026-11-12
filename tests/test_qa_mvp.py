import json
import os
from pathlib import Path
import shutil
import sys
from threading import Event
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from changelens.core import index_repository
from changelens.qa_review import model_findings, review_items, source_evidence
from changelens.qa_ui import REVIEW_PAGE
from changelens.ranking import resources
from changelens.refactoring import apply_reviewed_patch, preview_refactoring, undo_reviewed_patch
from changelens.runner import run_project_tests
from changelens.workbench import MainWindow
from changelens.workspace import Document, analyze_workspace, capture_baseline


CASES = [
    ("calc.py", 'def total(amount):\n    """Add the fixed fee of 10."""\n    return amount + 10\n',
     "test_calc.py", "from calc import total\ndef test_total(): assert total(5) == 15\n"),
    ("calc.mjs", "/** Add the fixed fee of 10. */\nexport function total(amount) { return amount + 10; }\n",
     "calc.test.mjs", "import test from 'node:test';\nimport assert from 'node:assert/strict';\n"
     "import {total} from './calc.mjs';\ntest('adds fee', () => assert.equal(total(5), 15));\n"),
    ("calc.tsx", "/** Add the fixed fee of 10. */\nexport function total(amount: number): number { return amount + 10; }\n"
     "export function Summary() { return <span>{total(5)}</span>; }\n",
     "calc.test.ts", "import {test, expect} from 'vitest';\nimport {total} from './calc';\n"
     "test('adds fee', () => expect(total(5)).toBe(15));\n"),
    ("lib/calc.dart", "/// Add the fixed fee of 10.\nint total(int amount) { return amount + 10; }\n",
     "test/calc_test.dart", "import 'package:flutter_test/flutter_test.dart';\n"
     "import 'package:change_lens_flutter_demo/calc.dart';\n"
     "void main() { test('adds fee', () => expect(total(5), 15)); }\n"),
]


def write(root, path, source):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.encode("utf-8"))


def prepare(root, case):
    path, clean, test_path, test_source = case
    write(root, path, clean)
    write(root, test_path, test_source)
    if path.endswith(".dart"):
        write(root, "pubspec.yaml", "name: change_lens_flutter_demo\n"
              "environment:\n  sdk: '>=3.3.0 <4.0.0'\ndependencies:\n  flutter:\n    sdk: flutter\n"
              "dev_dependencies:\n  flutter_test:\n    sdk: flutter\n")
    if path.endswith(".tsx"):
        write(root, "package.json", '{"name":"controlled-tsx","type":"module","private":true}')


def idle(app, window, timeout=25):
    limit = time.monotonic() + timeout
    while time.monotonic() < limit:
        app.processEvents()
        if window.worker is None and window.ai_worker is None:
            app.processEvents()
            if window.worker is None and window.ai_worker is None:
                return
        time.sleep(.01)
    pytest.fail("Workbench did not become idle")


@pytest.fixture
def workbench(tmp_path, monkeypatch):
    monkeypatch.setenv("CHANGELENS_TEST_NO_AI", "1")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "settings"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    yield app, window
    idle(app, window, 130)
    window.close()
    app.processEvents()


def model_rows(window):
    return [window.qa_items.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
            for i in range(window.qa_items.topLevelItemCount())
            if window.qa_items.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)["kind"] == "Model interpretation"]


def click_code(editor, text):
    cursor = editor.document().find(text)
    assert not cursor.isNull()
    cursor.setPosition(cursor.selectionStart() + 1)
    QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=editor.cursorRect(cursor).center())


def test_click_variable_refactors_in_editor_and_undoes(tmp_path, workbench):
    root = tmp_path / "project"
    source = "def total(amount):\n    subtotal = amount\n    return subtotal + 1\n# comment_word\n"
    write(root, "app.py", source)
    write(root, "test_app.py", "from app import total\ndef test_total(): assert total(2) == 3\n")
    app, window = workbench
    window.open_path(root)
    idle(app, window)
    window.navigate(0)
    window.pages.finish_transition()
    editor = window.current_editor()
    click_code(editor, "comment_word")
    assert window.inline_refactor is None
    click_code(editor, "subtotal")
    panel = window.inline_refactor
    assert panel and panel.isVisible() and panel.rename.isVisible()
    assert editor.hasFocus()
    panel.new_name.setText("net_amount")
    panel.rename.click()
    idle(app, window)
    assert window.pages.currentIndex() == 0 and window.inline_refactor is panel
    assert "return net_amount + 1" in panel.diff.toPlainText(), panel.status.text()
    assert (root / "app.py").read_bytes() == source.encode()
    panel.apply.click()
    idle(app, window)
    assert window.pages.currentIndex() == 0 and panel.undo.isVisible(), window.status.text()
    assert "return net_amount + 1" in editor.toPlainText()
    panel.undo.click()
    idle(app, window)
    assert window.pages.currentIndex() == 0 and editor.toPlainText() == source
    assert (root / "app.py").read_bytes() == source.encode()
    click_code(editor, "total")
    panel = window.inline_refactor
    panel.new_name.setText("invoice_total")
    panel.rename.click()
    idle(app, window)
    assert panel.files.isVisible() and panel.files.count() == 2
    panel.files.setCurrentText("test_app.py")
    assert "+from app import invoice_total" in panel.diff.toPlainText()


def test_click_javascript_function_previews_local_ai_in_editor(tmp_path, monkeypatch, workbench):
    root = tmp_path / "project"
    source = "function first() { return 1; } function second() { return 2 + 0; }\n"
    write(root, "app.js", source)
    app, window = workbench
    window.open_path(root)
    idle(app, window)
    window.navigate(0)
    window.pages.finish_transition()
    editor = window.current_editor()
    click_code(editor, "second")
    panel = window.inline_refactor
    assert panel and panel.rename.isVisible() and panel.improve.isVisible()

    def propose(code, *args, **kwargs):
        assert code.startswith("function second")
        return '{"code":"function second() { return 2; }","explanation":"Return the same value directly."}'

    monkeypatch.setattr(window.local_ai, "assist", propose)
    panel.improve.click()
    idle(app, window)
    assert window.pages.currentIndex() == 0 and "return 2;" in panel.diff.toPlainText(), panel.status.text()
    assert (root / "app.js").read_bytes() == source.encode()
    editor.setFocus()
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    assert window.inline_refactor is None


@pytest.mark.skipif(not (resources() / "refactoring/node_modules/typescript/lib/typescript.js").is_file(),
                    reason="TypeScript language service prepared by setup")
@pytest.mark.parametrize("extension", [".js", ".ts", ".jsx", ".tsx"])
def test_web_refactor_service_renames_across_files_and_extracts(tmp_path, monkeypatch, extension):
    root = tmp_path / "project"
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "settings"))
    path = "calc" + extension
    annotation = ": number" if extension in {".ts", ".tsx"} else ""
    source = f"// 😀\nexport function total(n{annotation}) {{\n  return n * 2 + 1;\n}}\n"
    if extension in {".jsx", ".tsx"}:
        source += "export function View() { return <span>{total(4)}</span>; }\n"
    consumer = "import {total} from './calc';\nexport const result = total(4);\n"
    write(root, path, source)
    write(root, "caller.js", consumer)
    snapshot = index_repository(root)
    rename = preview_refactoring(snapshot, path, "rename", "invoiceTotal", source.index("total"))
    receipt = apply_reviewed_patch(snapshot, rename)
    assert (root / "caller.js").read_text() == consumer.replace("total", "invoiceTotal")
    undo_reviewed_patch(root, receipt)
    assert (root / path).read_bytes() == source.encode()
    start = source.index("n * 2")
    for operation, name in [("extract_variable", "doubled"), ("extract_method", "scale")]:
        patch = preview_refactoring(snapshot, path, operation, name, start, start + len("n * 2"))
        assert name in patch["files"][0]["after"]
        assert (root / path).read_bytes() == source.encode()


@pytest.mark.skipif(not (resources() / "refactoring/node_modules/typescript/lib/typescript.js").is_file(),
                    reason="TypeScript language service prepared by setup")
def test_typescript_mouse_selection_extracts_and_applies_in_editor(tmp_path, workbench):
    root = tmp_path / "project"
    source = "export function total(n: number) {\n  return n * 2 + 1;\n}\n"
    write(root, "calc.ts", source)
    app, window = workbench
    window.open_path(root)
    idle(app, window)
    window.navigate(0)
    window.pages.finish_transition()
    editor = window.current_editor()
    editor.moveCursor(QTextCursor.MoveOperation.End)
    editor.insertPlainText("// draft\n")
    source += "// draft\n"
    cursor = editor.document().find("n * 2")
    last = editor.cursorRect(cursor).center()
    cursor.setPosition(cursor.selectionStart())
    first = editor.cursorRect(cursor).center()
    viewport = editor.viewport()
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=first)
    event = QMouseEvent(QEvent.Type.MouseMove, QPointF(last), QPointF(viewport.mapToGlobal(last)),
                        Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    app.sendEvent(viewport, event)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=last)
    panel = window.inline_refactor
    assert panel and editor.textCursor().selectedText() == "n * 2"
    assert panel.save_file.isVisible()
    panel.save_file.click()
    assert not editor.document().isModified() and editor.textCursor().selectedText() == "n * 2"
    panel.extraction.setCurrentIndex(panel.extraction.findData("extract_variable"))
    panel.new_name.setText("doubled")
    panel.rename.click()
    idle(app, window)
    assert panel.apply.isVisible(), panel.status.text()
    assert "const doubled" in panel.diff.toPlainText()
    panel.apply.click()
    idle(app, window)
    assert window.pages.currentIndex() == 0 and panel.undo.isVisible(), panel.status.text()
    assert "const doubled" in (root / "calc.ts").read_text()
    panel.undo.click()
    idle(app, window)
    assert (root / "calc.ts").read_bytes() == source.encode()


@pytest.mark.skipif(not shutil.which("node") or not (resources() / "refactoring/node_modules/typescript/lib/typescript.js").is_file(),
                    reason="Node and prepared TypeScript language service required")
def test_javascript_refactors_keep_real_test_passing(tmp_path, monkeypatch):
    root = tmp_path / "project"
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "settings"))
    source = "export function total(n) {\n  return n * 2 + 1;\n}\n"
    write(root, "calc.mjs", source)
    write(root, "calc.test.mjs", "import test from 'node:test';\nimport assert from 'node:assert/strict';\n"
          "import {total} from './calc.mjs';\ntest('totals', () => assert.equal(total(4), 9));\n")
    snapshot = index_repository(root)
    for operation, selected, name in [("rename", "total", "invoiceTotal"),
                                      ("extract_method", "n * 2", "scale"),
                                      ("extract_variable", "n * 2", "doubled")]:
        start = source.index(selected)
        patch = preview_refactoring(snapshot, "calc.mjs", operation, name, start, start + len(selected))
        receipt = apply_reviewed_patch(snapshot, patch)
        changed = index_repository(root)
        tests = [sid for sid, symbol in changed.symbols.items() if symbol.is_test]
        result = run_project_tests(changed, tests, shutil.which("node"), trusted=True)
        assert result["status"] == "passed", result["output"]
        undo_reviewed_patch(root, receipt)
        assert (root / "calc.mjs").read_bytes() == source.encode()


def test_first_time_sample_rename_with_tests(tmp_path, monkeypatch, workbench):
    app, window = workbench
    window.navigate(4)
    assert window.refactor_sample.isEnabled() and not window.refactor_choose.isEnabled()
    window.refactor_sample.click()
    idle(app, window)
    assert window.pages.currentIndex() == REVIEW_PAGE and window.tool_window.page_index == 4
    assert window.patch and window.patch["new"] == "calculate_total", window.status.text()
    target = Path(window.snapshot.root) / "invoice.py"
    original = target.read_bytes()
    assert b"def calculate_invoice_total(" in original
    assert "test_invoice.py" in window.patch_checks.text()
    window.interpreter.setText(sys.executable)
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.No)
    window.apply_test_button.click()
    assert target.read_bytes() == original and window.worker is None
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes)
    window.apply_test_button.click()
    idle(app, window)
    assert b"def calculate_total(" in target.read_bytes()
    assert window.pages.currentIndex() == REVIEW_PAGE and window.tool_window.page_index == 3
    assert window.report["test_run"]["status"] == "passed", window.validation_view.toPlainText()
    window.undo_from_tests.click()
    idle(app, window)
    assert target.read_bytes() == original


def test_function_picker_renames_decorated_async_function(tmp_path, workbench):
    root = tmp_path / "project"
    write(root, "app.py", "def decorate(f): return f\n\n@decorate\nasync def calculate():\n    return 7\n")
    app, window = workbench
    window.open_path(root)
    idle(app, window)
    window.navigate(4)
    window.refactor_choose.click()
    window.picker.query.setText("calculate")
    window.picker.activate()
    window.new_name.setText("calculate_total")
    window.preview_button.click()
    idle(app, window)
    assert window.patch and "async def calculate_total()" in window.patch["diff"], window.status.text()


def test_refactor_preview_rejects_stale_editor_offsets(tmp_path, workbench):
    root = tmp_path / "project"
    original = "def calculate():\n    return 7\n"
    write(root, "app.py", original)
    app, window = workbench
    window.open_path(root)
    idle(app, window)
    window.open_file("app.py", 1)
    editor = window.current_editor()
    editor.setTextCursor(editor.document().find("calculate"))
    window.navigate(4)
    window.new_name.setText("calculate_total")
    external_edit = "def other():\n    return 8\n\n" + original
    write(root, "app.py", external_edit)
    window.preview()
    idle(app, window)
    assert window.patch is None
    assert "saved file changed on disk" in window.banner.text()
    assert (root / "app.py").read_text() == external_edit


def test_function_picker_pins_the_selected_javascript_declaration(tmp_path, monkeypatch, workbench):
    root = tmp_path / "project"
    source = "function first() { return 1; } function second() { return 2 + 0; }\n"
    write(root, "app.js", source)
    app, window = workbench
    window.open_path(root)
    idle(app, window)
    window.navigate(4)
    window.refactor_choose.click()
    window.picker.query.setText("second")
    window.picker.activate()
    window.assistant_ready = True

    def propose(code, *args, **kwargs):
        assert code.startswith("function second")
        return '{"code":"function second() { return 2; }","explanation":"Return the same value directly."}'

    monkeypatch.setattr(window.local_ai, "assist", propose)
    window.preview_button.click()
    idle(app, window)
    assert window.patch, window.refactor_context.text()
    assert window.patch["files"][0]["after"] == source.replace("2 + 0", "2")
    assert (root / "app.js").read_bytes() == source.encode()


@pytest.mark.parametrize("case", CASES, ids=["python", "javascript", "tsx", "flutter"])
def test_native_review_model_contract_and_apply_undo(tmp_path, monkeypatch, workbench, case):
    root = tmp_path / "project"
    prepare(root, case)
    path, clean, test_path, _ = case
    app, window = workbench
    window.open_path(root)
    idle(app, window)
    assert window.pages.currentIndex() == REVIEW_PAGE
    assert "No saved changes" in window.qa_scope.text()
    assert not window.qa_model.isEnabled()
    monkeypatch.setattr(window.local_ai, "activate", lambda *_: None)

    def request(endpoint, payload, cancel, timeout):
        if "verdict" in payload["format"]["properties"]:
            return {"message": {"content": '{"verdict":"conflicts"}'}}
        excerpts = json.loads(payload["messages"][1]["content"])
        changed = next((row for row in excerpts if "amount - 10" in row["code"]), None)
        rows = [] if not changed else [{
            "evidence_id": changed["id"], "title": "Fee is subtracted",
            "witness": "amount - 10", "basis": "amount + 10",
            "consequence": "total(5) returns -5 instead of 15.",
            "verification": "run_relevant_tests",
        }]
        return {"message": {"content": json.dumps({"findings": rows})}}

    monkeypatch.setattr(window.local_ai, "request", request)
    window.open_file(path, 2)
    window.review_saved("function")
    idle(app, window)
    window.qa_model.click()
    idle(app, window)
    assert not model_rows(window)
    assert "no findings" in window.qa_model_status.text()
    write(root, path, clean.replace("amount + 10", "amount - 10"))
    window.qa_changes.click()
    idle(app, window)
    assert any(sid.startswith(test_path + ":") for sid in window.checked_tests())
    assert any(row["kind"] == "Impact evidence" for row in review_items(window.report))
    window.qa_model.click()
    idle(app, window)
    assert model_rows(window)[0]["path"] == path
    assert "returns -5" in window.qa_detail.toPlainText()
    assert "Tests not run" in window.qa_scope.text()
    assert "Why it matters" in window.qa_detail.toPlainText()
    assert "Current code" not in window.qa_detail.toPlainText()
    window.qa_show_evidence.click()
    assert "Current code\namount - 10" in window.qa_detail.toPlainText()
    window.assistant_ready = True
    fixed = {"calc.py": 'def total(amount):\n    """Add the fixed fee of 10."""\n    return 10 + amount\n',
             "calc.mjs": "function total(amount) { return 10 + amount; }",
             "calc.tsx": "function total(amount: number): number { return 10 + amount; }",
             "lib/calc.dart": "int total(int amount) { return 10 + amount; }"}[path]
    def propose(source, instruction, **options):
        assert options["fix"] and "matches the quoted expectation" in instruction
        assert json.loads(options["context"])["expected behavior"] == "amount + 10"
        return json.dumps({"code": fixed, "explanation": "Use the fixed fee plus the amount."})

    monkeypatch.setattr(window.local_ai, "assist", propose)
    before = (root / path).read_bytes()
    window.qa_fix.click()
    idle(app, window)
    assert window.pages.currentIndex() == 4
    assert window.current_document().path == root / path
    assert window.patch is not None, window.refactor_context.text()
    assert test_path in window.patch_checks.text()
    assert (root / path).read_bytes() == before
    assert window.apply_button.text() == "Apply this fix"
    window.apply_button.click()
    idle(app, window)
    assert window.pages.currentIndex() == REVIEW_PAGE and window.qa_undo.isEnabled(), (
        window.status.text(), window.banner.text(), window._pending_error)
    assert "Fix applied" in window.qa_scope.text()
    assert any(sid.startswith(test_path + ":") for sid in window.checked_tests())
    assert b"10 + amount" in (root / path).read_bytes()
    window.qa_undo.click()
    idle(app, window)
    assert not window.qa_undo.isEnabled()
    assert (root / path).read_bytes() == before


def test_removed_and_invalid_source_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "settings"))
    root = tmp_path / "project"
    write(root, "calc.py", "def total(): return 1\n")
    write(root, "use.py", "from calc import total\ndef use(): return total()\n")
    capture_baseline(index_repository(root))
    (root / "calc.py").unlink()
    write(root, "broken.py", "def broken(\n")
    snapshot, report = analyze_workspace(root)
    rows = review_items(report)
    assert any(row.get("historical") and row["path"] == "calc.py" and "use.py:2" in row["detail"]
               for row in rows)
    assert any(row["kind"] == "Parser error" and row["path"] == "broken.py" for row in rows)
    excerpts, _ = source_evidence(snapshot, report, None)
    assert any(row["path"] == "calc.py" and row["side"] == "baseline" for row in excerpts)


def test_model_rejects_fabricated_citation(workbench, monkeypatch):
    _, window = workbench
    monkeypatch.setattr(window.local_ai, "activate", lambda *_: None)
    monkeypatch.setattr(window.local_ai, "request", lambda *args, **kwargs: {"message": {"content":
        '{"findings":[{"evidence_id":"E99","witness":"return 5","basis":"return 5","title":"Bug","consequence":"Wrong","verification":"Test"}]}'}})
    with pytest.raises(ValueError, match="cited unavailable evidence"):
        model_findings(window.local_ai, [{"id": "E1", "code": "return 5"}])


def test_unsaved_review_cancel_and_late_model_result(tmp_path, monkeypatch, workbench):
    root = tmp_path / "first"
    prepare(root, CASES[0])
    app, window = workbench
    window.open_path(root)
    idle(app, window)
    window.open_file("calc.py", 3)
    editor = window.current_editor()
    editor.textCursor().insertText("# Unsaved draft ")
    window.qa_changes.click()
    idle(app, window)
    assert editor.document().isModified() and "Unsaved draft" in editor.toPlainText()
    assert "Unsaved draft" not in (root / "calc.py").read_text(encoding="utf-8")
    assert not window.qa_model.isEnabled()
    editor.undo()
    window.qa_focus.click()
    idle(app, window)

    monkeypatch.setattr(window.local_ai, "activate", lambda *_: None)
    started = Event()

    def slow_request(endpoint, payload, cancel, timeout):
        started.set()
        cancel.wait(8)
        return {"message": {"content":
            '{"findings":[{"evidence_id":"E1","title":"Old result","consequence":"Old scope","verification":"Inspect"}]}'}}

    monkeypatch.setattr(window.local_ai, "request", slow_request)
    window.qa_model.click()
    assert started.wait(3)
    window.qa_cancel.click()
    idle(app, window)
    assert not model_rows(window) and "cancelled" in window.qa_model_status.text().lower()
    started.clear()
    window.qa_model.click()
    assert started.wait(3)
    last = tmp_path / "last"
    prepare(last, CASES[1])
    window.open_path(last)
    idle(app, window)
    assert Path(window.snapshot.root) == last and window.pages.currentIndex() == REVIEW_PAGE
    assert not model_rows(window) and "Old scope" not in window.qa_detail.toPlainText()


def test_missing_runner_visible_in_tests(tmp_path, monkeypatch, workbench):
    root = tmp_path / "project"
    prepare(root, CASES[1])
    app, window = workbench
    window.open_path(root)
    idle(app, window)
    window.open_file("calc.mjs", 2)
    window.qa_focus.click()
    idle(app, window)
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr("changelens.js_runner.detect_node", lambda *_: "")
    window.interpreter.clear()
    window.qa_tests.click()
    window.validate_button.click()
    idle(app, window)
    assert "Install Node.js" in window.run_summary.text()
    assert "test_run" not in window.report


def test_patch_rolls_back_partial_write_and_undo_detects_conflict(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "settings"))
    root = tmp_path / "project"
    before = b"def total():\r\n    return 1\n"
    for path in ("a.py", "b.py"):
        write(root, path, before.decode())
    snapshot = index_repository(root)
    patch = {"snapshot": snapshot.id, "operation": "rename", "files": [
        {"path": path, "before": before.decode().replace("\r\n", "\n"),
         "after": "def total():\n    return 2\n"} for path in ("a.py", "b.py")]}
    save = Document.save_raw

    def fail_second(document, raw, origin="save"):
        if document.path.name == "b.py":
            raise PermissionError("simulated locked file")
        return save(document, raw, origin)

    with monkeypatch.context() as guarded:
        guarded.setattr(Document, "save_raw", fail_second)
        with pytest.raises(ValueError, match="Completed writes rolled back"):
            apply_reviewed_patch(snapshot, patch)
    assert (root / "a.py").read_bytes() == (root / "b.py").read_bytes() == before
    receipt = apply_reviewed_patch(snapshot, patch)
    applied = (root / "a.py").read_bytes()
    assert applied.startswith(b"def total():\r\n")
    write(root, "b.py", "def total(): return 3\n")
    with pytest.raises(ValueError, match="changed after Apply"):
        undo_reviewed_patch(root, receipt)
    assert (root / "a.py").read_bytes() == applied
    (root / "b.py").write_bytes(applied)
    undo_reviewed_patch(root, receipt)
    assert (root / "a.py").read_bytes() == (root / "b.py").read_bytes() == before


def test_document_retries_windows_sharing_lock_and_rechecks_source(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "settings"))
    path = tmp_path / "sample.py"
    path.write_bytes(b"value = 1\n")
    document = Document(path)
    replace = os.replace
    calls = []

    def locked_once(source, target):
        calls.append(target)
        if len(calls) == 1:
            error = PermissionError("sharing violation")
            error.winerror = 32
            raise error
        replace(source, target)

    monkeypatch.setattr("changelens.workspace.os.replace", locked_once)
    document.save("value = 2\n")
    assert len(calls) == 2 and path.read_bytes() == b"value = 2\n"

    def changed_while_locked(source, target):
        target.write_bytes(b"value = 3\n")
        error = PermissionError("sharing violation")
        error.winerror = 32
        raise error

    monkeypatch.setattr("changelens.workspace.os.replace", changed_while_locked)
    with pytest.raises(ValueError, match="changed while saving"):
        document.save("value = 4\n")
    assert path.read_bytes() == b"value = 3\n"


@pytest.mark.skipif(os.environ.get("CHANGELENS_MVP_LIVE") != "1",
                    reason="Requires local Ollama and prepared Vitest and Flutter fixtures")
@pytest.mark.parametrize("case", CASES, ids=["python", "javascript", "tsx", "flutter"])
def test_live_qa_model_and_test_runner(tmp_path, monkeypatch, workbench, case):
    root = tmp_path / "project"
    path, clean, test_path, _ = case
    prepare(root, case)
    if path.endswith(".tsx"):
        shutil.copytree(Path(os.environ["CHANGELENS_MVP_VITEST"]) / "node_modules", root / "node_modules")
    elif path.endswith(".dart"):
        config = Path(os.environ["CHANGELENS_MVP_FLUTTER"]) / ".dart_tool" / "package_config.json"
        target = root / ".dart_tool" / "package_config.json"
        target.parent.mkdir()
        value = json.loads(config.read_text(encoding="utf-8"))
        for package in value["packages"]:
            uri = package["rootUri"]
            if package["name"] != "change_lens_flutter_demo" and not uri.startswith("file:"):
                package["rootUri"] = (config.parent / uri).resolve().as_uri()
        target.write_text(json.dumps(value), encoding="utf-8")
        graph = config.with_name("package_graph.json")
        if graph.is_file():
            shutil.copy2(graph, target.with_name(graph.name))
    app, window = workbench
    window.open_path(root)
    idle(app, window)
    window.open_file(path, 2)
    window.review_saved("file")
    idle(app, window)
    window.qa_model.click()
    idle(app, window, 130)
    clean_status, clean_findings = window.qa_model_status.text(), model_rows(window)
    print(path, "clean", clean_status, clean_findings)

    before = clean.replace("amount + 10", "amount - 10")
    write(root, path, before)
    window.qa_changes.click()
    idle(app, window)
    window.qa_model.click()
    idle(app, window, 130)
    rows = model_rows(window)
    print(path, "seeded", window.qa_model_status.text(), rows)
    assert any(row["path"] == path and any(word in row["detail"].lower() for word in
               ("subtract", "decreas", "-5", "lower", "instead")) and row["next"] for row in rows)

    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.No)
    window.qa_tests.click()
    if path.endswith(".py"):
        window.interpreter.setText(sys.executable)
    window.validate_button.click()
    assert "test_run" not in window.report and window.worker is None
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes)
    window.validate_button.click()
    idle(app, window, 130)
    result = window.report.get("test_run")
    assert result and result["status"] == "failed", (window.run_summary.text(), window.validation_view.toPlainText())
    assert "adds fee" in result["output"] or "test_total" in result["output"], result["output"]
    print(path, "seeded test", window.run_summary.text())

    window.workspace_buttons[REVIEW_PAGE].click()
    window.assistant_ready = True
    original = (root / path).read_bytes()
    window.qa_fix.click()
    idle(app, window, 130)
    assert window.patch and window.patch["syntax_validation"] == "passed", window.refactor_context.text()
    assert window.patch["finding_title"] == rows[0]["title"]
    assert test_path in window.patch_checks.text()
    assert (root / path).read_bytes() == original
    window.apply_button.click()
    idle(app, window)
    window.qa_tests.click()
    window.validate_button.click()
    idle(app, window, 130)
    result = window.report.get("test_run")
    assert result and result["status"] == "passed", (window.run_summary.text(), window.validation_view.toPlainText())
    print(path, "test after proposed fix", window.run_summary.text())
    window.workspace_buttons[REVIEW_PAGE].click()
    assert window.qa_undo.isEnabled(), (window.status.text(), window.worker, window.applied_patch)
    window.qa_undo.click()
    idle(app, window)
    assert (root / path).read_bytes() == original, (window.status.text(), window.banner.text())
    assert not clean_findings and "no findings" in clean_status.lower(), (clean_status, clean_findings)
