"""Exercise the native UI and packaged worker, then exit with a machine-readable report."""
import json
from pathlib import Path
import sys
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from .workbench import MainWindow
from .ranking import resources
from .completion import complete_python


def run(output: Path):
    import os
    import tempfile
    import ast
    with_ai="--with-local-ai" in sys.argv
    if not with_ai:os.environ["CHANGELENS_TEST_NO_AI"]="1"
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    stage = 0
    started = time.monotonic()
    failures = []
    ai_directory=None
    ai_completion_source='def add(a, b):\n    """Return the sum of a and b."""\n    return a\n'
    timer = QTimer()

    def finish(error=None):
        timer.stop()
        if error:
            failures.append(str(error))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"passed": not failures, "failures": failures, "stages_completed": stage,
            "snapshot": window.snapshot.id if window.snapshot else None,
            "report": window.report, "patch": window.patch}, indent=2), encoding="utf-8")
        window.grab().save(str(output.with_suffix(".png")))
        if window.worker:
            window.cancel()
        else:
            window.close()
        app.exit(1 if failures else 0)

    def tick():
        nonlocal stage, ai_directory
        if time.monotonic() - started > (180 if with_ai else 90):
            if window.worker:
                window.cancel()
                return
            finish("Timed out")
            return
        if window.worker is not None or window.ai_worker is not None:
            return
        if window._pending_error:
            finish(window._pending_error)
            return
        try:
            if stage == 0:
                window.open_path(resources() / "demo")
            elif stage == 1:
                assert window.snapshot is not None
                window.select_symbol("invoice.py:calculate_invoice_total")
                window.analyze_selected()
            elif stage == 2:
                assert window.report and len(window.report["tests"]) == 7
                editor=window.current_editor()
                editor.moveCursor(__import__("PySide6.QtGui",fromlist=["QTextCursor"]).QTextCursor.MoveOperation.Start)
                assert editor.find("subtotal")
                window.new_name.setText("net_amount")
                window.preview()
            elif stage == 3:
                assert window.patch and "net_amount" in window.patch["diff"]
                window.validate_demo(False)
            elif stage == 4:
                result = window.report["demo_validation"]
                assert result["full"]["returncode"] == 0, result
                window.validate_demo(True)
            elif stage == 5:
                result = window.report["demo_validation"]
                assert result["failing_test_recall"] == 1, result
                assert result["full"]["returncode"] == 1, result
                window.train()
            elif stage == 6:
                assert "training_pairs" in window.validation_view.toPlainText()
                window.quick_open()
                window.picker.query.setText("invoice.py")
                assert window.picker.results.count() >= 1
                window.picker.reject()
                window.command_palette()
                window.picker.query.setText("View: Editor")
                assert window.picker.results.count() == 1
                window.picker.activate()
                completions=complete_python("message = 'hello'\nmessage.up",str(resources()/"demo"/"completion_check.py"),2,10,str(resources()/"demo"))
                assert "upper" in {row["name"] for row in completions},completions
                window.navigate(0)
                assert window.comparison.currentData()=="auto"
                if not with_ai:
                    finish()
                    return
            elif stage == 7:
                from .core import app_dir
                ai_directory=tempfile.TemporaryDirectory(prefix="self-test-ai-",dir=app_dir())
                root=Path(ai_directory.name)
                (root/"a.py").write_text("def total(value):\n    result = value + 1\n    return result\n",encoding="utf-8")
                (root/"b.py").write_text(ai_completion_source,encoding="utf-8")
                window.open_path(root)
            elif stage == 8:
                window.connect_ai()
            elif stage == 9:
                assert window.ai_ready and window.assistant_ready,"Prepare the presentation models before the AI self-test."
                window.open_file("b.py"); window.navigate(0); editor=window.current_editor()
                editor.moveCursor(__import__("PySide6.QtGui",fromlist=["QTextCursor"]).QTextCursor.MoveOperation.Start)
                assert editor.find("return a")
                editor.textCursor().insertText("return ")
                window.activateWindow(); editor.setFocus(); app.processEvents(); window.request_ai_completion()
            elif stage == 10:
                editor=window.current_editor(); assert editor.ghost_text,"The local model did not provide an inline completion."
                window.grab().save(str(output.with_name(output.stem+"_completion.png")))
                editor.accept_ghost(); ast.parse(editor.toPlainText())
                editor.set_code(ai_completion_source)
                window.open_file("a.py"); window.suggest_rewrite()
            elif stage == 11:
                assert window.patch and window.patch["operation"]=="ai_rewrite"
                assert window.patch["syntax_validation"]=="passed"
                assert (Path(ai_directory.name)/"a.py").read_text(encoding="utf-8")=="def total(value):\n    result = value + 1\n    return result\n"
                window.navigate(4); window.grab().save(str(output.with_name(output.stem+"_rewrite.png")))
                window.open_path(resources()/"demo")
            elif stage == 12:
                assert len(window.lens_view.map.nodes)==8
                window.grab().save(str(output.with_name(output.stem+"_lens.png")))
                window.explain_impact("test_invoice.py:test_invoice_route")
            elif stage == 13:
                assert window.ai_answer.toPlainText().strip()
                assert "test_invoice_route" in window.ai_context_label.text()
                window.navigate(7); finish(); return
            stage += 1
        except Exception as exc:
            finish(repr(exc))

    # Avoid modal dialogs blocking unattended verification.
    from PySide6.QtWidgets import QMessageBox
    QMessageBox.warning = lambda *args: None
    timer.timeout.connect(tick)
    timer.start(100)
    return app.exec()
