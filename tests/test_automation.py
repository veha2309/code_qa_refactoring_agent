import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import subprocess
import time

from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from changelens.workspace import analyze_workspace, load_baseline
from changelens.workbench import MainWindow


def write(root, path, source):
    target=root/path; target.parent.mkdir(parents=True,exist_ok=True); target.write_text(source,encoding="utf-8")


def until(app, predicate, timeout=8):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():return
        time.sleep(.015)
    assert predicate(), "Automatic workflow did not settle"


def test_first_open_records_comparison_without_overwriting_on_reopen(tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"settings"))
    root=tmp_path/"project"; root.mkdir()
    write(root,"a.py","def total(): return 1\n")
    snapshot,report=analyze_workspace(root)
    initial=load_baseline(str(root))
    assert report["comparison_context"]["created"]
    assert not report["changes"]["seeds"]
    write(root,"a.py","def total(): return 2\n")
    _,reopened=analyze_workspace(root)
    assert reopened["changes"]["seeds"]==["a.py:total"]
    assert not reopened["comparison_context"]["created"]
    assert load_baseline(str(root))["captured_at"]==initial["captured_at"]


def test_automatic_comparison_prefers_git_and_handles_unborn_repository(tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"settings"))
    root=tmp_path/"project"; root.mkdir(); write(root,"a.py","def total(): return 1\n")
    def git(*args):subprocess.run(["git","-C",str(root),*args],check=True,capture_output=True)
    git("init")
    _,unborn=analyze_workspace(root)
    assert unborn["comparison"]=="baseline"
    git("add","."); git("-c","user.name=Test","-c","user.email=test@example.invalid","commit","-m","sample")
    write(root,"a.py","def total(): return 2\n")
    _,changed=analyze_workspace(root)
    assert changed["comparison"]=="git" and changed["changes"]["seeds"]==["a.py:total"]


def test_open_edit_save_checks_and_review_without_setup(tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"settings"))
    root=tmp_path/"project"; root.mkdir()
    write(root,"a.py","def total(value):\n    return value + 1\n")
    marker=tmp_path/"executed"
    write(root,"test_a.py",f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\nfrom a import total\ndef test_total(): assert total(1) == 2\n")
    app=QApplication.instance() or QApplication([]); window=MainWindow(); window.show(); window.open_path(root)
    until(app,lambda:window.worker is None and window.report is not None)
    assert window.comparison.currentData()=="auto" and not window.comparison.isVisible()
    assert not window.interpreter.isVisible() and not window.timeout.isVisible()
    assert window.pages.currentIndex()==6
    window.navigate(0)
    editor=window.current_editor(); editor.moveCursor(QTextCursor.MoveOperation.Start); assert editor.find("+ 1")
    editor.textCursor().insertText("+ 2"); window.save_current()
    until(app,lambda:window.worker is None and not window.report_stale and window.report["summary"]["recommended_tests"]==1)
    assert window.pages.currentIndex()==0
    assert window.checked_tests()==["test_a.py:test_total"]
    assert not marker.exists()  # Opening, saving and checking never execute the repository.
    window.analyze_changes(); until(app,lambda:window.worker is None)
    assert window.pages.currentIndex()==6 and window.review_items.topLevelItemCount()>=1
    Path("evaluation").mkdir(exist_ok=True); window.grab().save("evaluation/automated_review.png")
    window.review_item_opened(window.review_items.topLevelItem(0))
    assert window.pages.currentIndex()==1 and "+ 2" in window.changes_view.after.toPlainText()
    window.close(); app.processEvents()


def test_external_edits_refresh_clean_buffers_without_switching_pages(tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"settings"))
    root=tmp_path/"project"; root.mkdir(); write(root,"a.py","def total(): return 1\n")
    app=QApplication.instance() or QApplication([]); window=MainWindow(); window.show(); window.open_path(root)
    until(app,lambda:window.worker is None and window.report is not None)
    window.navigate(0)
    write(root,"a.py","def total(): return 3\n")
    until(app,lambda:window.worker is None and "return 3" in window.current_editor().toPlainText())
    assert window.pages.currentIndex()==0 and not window.report_stale
    write(root,"new folder/b.py","def created(): return 2\n")
    until(app,lambda:window.worker is None and "new folder/b.py" in window.snapshot.hashes)
    window.close(); app.processEvents()


def test_typed_rename_previews_automatically_but_does_not_apply(tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"settings"))
    root=tmp_path/"project"; root.mkdir(); original="def total(value):\n    return value + 1\n"; write(root,"a.py",original)
    app=QApplication.instance() or QApplication([]); window=MainWindow(); window.show(); window.open_path(root)
    until(app,lambda:window.worker is None and window.report is not None)
    editor=window.current_editor(); editor.moveCursor(QTextCursor.MoveOperation.Start); assert editor.find("total")
    window.prepare_rename(); window.new_name.clear(); QTest.keyClicks(window.new_name,"net_total")
    until(app,lambda:window.worker is None and window.patch is not None)
    assert "net_total" in window.patch["diff"] and (root/"a.py").read_text()==original
    assert window.apply_button.isEnabled()
    window.close(); app.processEvents()


def test_unsaved_edits_are_not_written_by_background_checks(tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"settings"))
    root=tmp_path/"project"; root.mkdir(); original="def total(): return 1\n"; write(root,"a.py",original)
    app=QApplication.instance() or QApplication([]); window=MainWindow(); window.show(); window.open_path(root)
    until(app,lambda:window.worker is None and window.report is not None)
    editor=window.current_editor(); editor.moveCursor(QTextCursor.MoveOperation.End); editor.insertPlainText("# unsaved\n")
    window.files_changed(str(root/"a.py")); window.automatic_check()
    assert window.worker is None and window.pending_check
    assert (root/"a.py").read_text()==original
    # Explicitly discard this test-owned buffer so no close dialog is required.
    editor.set_code(original); window.close(); app.processEvents()
