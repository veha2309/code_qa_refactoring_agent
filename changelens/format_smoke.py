"""Exercise bundled formatters and the native review/undo workflow."""
import json
import os
from pathlib import Path
import tempfile
import time


def run(output):
    os.environ['CHANGELENS_TEST_NO_AI']='1'
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from .core import app_dir
    from .formatting import format_document
    from .workbench import MainWindow
    app=QApplication.instance() or QApplication([]);window=MainWindow();window.show()
    directory=tempfile.TemporaryDirectory(prefix='format-smoke-',dir=app_dir());root=Path(directory.name)
    original='def total( amount,tax=0.1 ):\n return amount*(1+tax)\n'
    (root/'price.py').write_text(original,encoding='utf-8')
    (root/'test_price.py').write_text('from price import total\ndef test_total(): assert total(100) == 110\n',encoding='utf-8')
    checks=[];stage=0;started=time.monotonic();timer=QTimer()
    def screenshot(suffix):window.grab().save(str(output.with_name(output.stem+suffix+'.png')))
    def finish(error=None):
        timer.stop();output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps({'passed':error is None,'checks':checks,'failures':[str(error)] if error else []},indent=2),encoding='utf-8')
        window.close();app.exit(1 if error else 0)
    def tick():
        nonlocal stage
        if time.monotonic()-started>90:window.cancel();finish('Timed out');return
        if window.worker:return
        if window._pending_error:finish(window._pending_error);return
        try:
            if stage==0:
                for path,source in [('a.py',original),('a.tsx','export const A=()=> <div>{1+2}</div>'),('package.json','{"a":[1,2]}')]:
                    result=format_document(path,source);assert result['changed'];assert not format_document(path,result['after'])['changed'];checks.append('bundled '+result['engine']+' '+path)
                window.open_path(root)
            elif stage==1:
                window.analyze(['price.py:total'])
            elif stage==2:
                window.navigate(6);screenshot('_lens');window.open_file('price.py');window.navigate(0);screenshot('_editor');window.format_current()
            elif stage==3:
                preview=window.format_preview;assert preview.isVisible()
                preview.grab().save(str(output.with_name(output.stem+'_preview.png')))
                preview.apply_button.click();assert 'def total(amount, tax=0.1):' in window.current_editor().toPlainText()
                assert (root/'price.py').read_text(encoding='utf-8')==original
                checks.append('review applies to buffer only')
                window.current_editor().undo();assert window.current_editor().toPlainText()==original;checks.append('single undo restores source')
                window.format_current()
            elif stage==4:
                editor=window.current_editor();editor.insertPlainText('# new edit\n')
                window.format_preview.apply_button.click();assert not window.format_preview.apply_button.isEnabled()
                assert 'changed after' in window.format_preview.error.text();checks.append('stale preview rejected')
                window.format_preview.reject();editor.document().setModified(False);finish();return
            stage+=1
        except Exception as exc:finish(repr(exc))
    output.parent.mkdir(parents=True,exist_ok=True);timer.timeout.connect(tick);timer.start(100)
    return app.exec()
