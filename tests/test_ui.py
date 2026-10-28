import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication
from changelens.workbench import MainWindow
from PySide6.QtGui import QTextCursor
from changelens.widgets import DiffViewer
from changelens.ranking import resources


def test_minimal_workbench_pickers_and_panels(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"settings"))
    root=tmp_path/"project"; root.mkdir()
    (root/"alpha.py").write_text("def alpha():\n    return 1\n")
    (root/"beta.py").write_text("def beta():\n    return 2\n")
    app=QApplication.instance() or QApplication([])
    window=MainWindow(); window.show(); window.open_path(root); wait(app,window)
    assert window.inspector.isHidden()
    assert window.project_panel.isHidden()
    window.quick_open()
    window.picker.query.setText("beta")
    assert window.picker.results.count()==1
    window.picker.activate()
    assert window.current_document().path.name=="beta.py"
    window.command_palette()
    window.picker.query.setText("toggle project")
    assert window.picker.results.count()==1
    window.picker.activate()
    assert window.project_panel.isVisible()
    window.toggle_project(); window.toggle_outline()
    assert window.inspector.isVisible()
    window.toggle_outline(); window.navigate(1); window.navigate(0)
    assert window.current_document().path.name=="beta.py"
    window.close(); app.processEvents()


def test_recommendation_choices_and_stale_previews(tmp_path, monkeypatch):
    from PySide6.QtCore import Qt
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"settings"))
    root=tmp_path/"project"; root.mkdir()
    (root/"a.py").write_text("def total(amount):\n    return amount + 1\n")
    (root/"test_a.py").write_text("from a import total\ndef test_total(): assert total(1) == 2\ndef test_other(): pass\n")
    app=QApplication.instance() or QApplication([])
    window=MainWindow(); window.show(); window.open_path(root); wait(app,window)
    window.analyze_selected(); wait(app,window)
    assert not window.report_stale and window.validate_button.isEnabled()
    window.test_table.item(0,3).setCheckState(Qt.CheckState.Unchecked)
    window.show_weak.setChecked(True); window.show_weak.setChecked(False)
    assert not window.checked_tests()
    editor=window.current_editor(); editor.moveCursor(QTextCursor.MoveOperation.Start)
    assert editor.find("total")
    window.new_name.setText("net_total"); window.preview(); wait(app,window)
    assert window.patch and window.apply_button.isEnabled()
    editor.moveCursor(QTextCursor.MoveOperation.End); editor.insertPlainText("\n# work in progress\n")
    assert window.report_stale and window.patch_stale
    assert not window.apply_button.isEnabled() and not window.validate_button.isEnabled()
    assert not window.patch_button.isEnabled() and window.result_state.isVisible()
    window.save_current(); window.analyze_changes(); wait(app,window)
    # The first-open comparison point means no manual baseline is needed.
    assert not window.report_stale
    window.close(); app.processEvents()


def wait(app, window):
    deadline = time.monotonic() + 20
    while window.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert window.worker is None


def test_native_workflow(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    window.open_path(resources() / "demo")
    wait(app, window)
    assert window.snapshot and window.symbols.count() == 5
    window.select_symbol("invoice.py:calculate_invoice_total")
    window.analyze_selected()
    wait(app, window)
    assert window.report and window.test_table.rowCount() == 5
    assert any("invoice_route" in row["symbol"] for row in window.report["impact"])
    editor=window.current_editor()
    editor.moveCursor(QTextCursor.MoveOperation.Start)
    assert editor.find("subtotal")
    window.new_name.setText("net_amount")
    window.preview()
    wait(app, window)
    assert window.patch and "net_amount" in window.diff_view.toPlainText()
    window.navigate(0)
    app.processEvents()
    Path("evaluation").mkdir(exist_ok=True)
    window.grab().save("evaluation/desktop_preview.png")
    window.close()
    app.processEvents()


def test_edit_diff_refactor_apply_workflow(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"settings"))
    root=tmp_path/"project"; root.mkdir()
    original="def total(amount):\n    value = amount + 1\n    return value\n"
    (root/"a.py").write_text(original,encoding="utf-8")
    (root/"b.py").write_text("from a import total\ndef route():\n    return total(2)\n",encoding="utf-8")
    (root/"test_a.py").write_text("from a import total\ndef test_total():\n    assert total(2) == 3\n",encoding="utf-8")
    app=QApplication.instance() or QApplication([])
    window=MainWindow(); window.show(); window.open_path(root); wait(app,window)
    assert window.current_editor() and not window.current_editor().isReadOnly()
    window.capture_baseline(); wait(app,window)
    editor=window.current_editor(); editor.moveCursor(QTextCursor.MoveOperation.Start)
    assert editor.find("amount + 1")
    cursor=editor.textCursor(); cursor.insertText("amount + 2")
    window.save_current()
    assert "amount + 2" in (root/"a.py").read_text()
    window.analyze_changes(); wait(app,window)
    assert window.report["changes"]["seeds"]==["a.py:total"]
    window.navigate(1); app.processEvents(); window.grab().save("evaluation/workbench_changes.png")
    assert "amount + 1" in window.changes_view.before.toPlainText()
    assert "amount + 2" in window.changes_view.after.toPlainText()
    window.navigate(0); editor.moveCursor(QTextCursor.MoveOperation.Start); assert editor.find("total")
    assert window.old_name.text()=="total"
    window.new_name.setText("invoice_total"); window.preview(); wait(app,window)
    assert len(window.patch["files"])==3
    app.processEvents(); window.grab().save("evaluation/workbench_refactor.png")
    window.apply_patch(); wait(app,window)
    assert "invoice_total" in (root/"b.py").read_text()
    assert (tmp_path/"settings"/"ChangeLens"/"backups").is_dir()
    window.navigate(3); app.processEvents(); window.grab().save("evaluation/workbench_tests.png")
    window.close(); app.processEvents()


def test_side_by_side_diff_aligns_insertions():
    app=QApplication.instance() or QApplication([])
    diff=DiffViewer()
    diff.set_versions("a = 1\nreturn a\n","a = 1\nb = 2\nreturn a\n")
    assert diff.before.toPlainText().splitlines()==["a = 1","","return a"]
    assert diff.before.line_numbers==[1,None,2]
    assert diff.after.line_numbers==[1,2,3]
    assert diff.after.diff_lines=={1:"#15382e"}
    diff.close()
    app.processEvents()
