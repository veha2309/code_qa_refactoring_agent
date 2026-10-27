"""Offline packaged grammar + native JS/TS workflow verification."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import time


def run(output):
    os.environ['CHANGELENS_TEST_NO_AI']='1'
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    from .core import app_dir, index_repository
    from .syntax import parse_unit
    from .ranking import resources
    from .runner import run_project_tests
    from .workbench import MainWindow
    app=QApplication.instance() or QApplication([])
    directory=tempfile.TemporaryDirectory(prefix='language-smoke-',dir=app_dir())
    root=Path(directory.name); shutil.copytree(resources()/'web_demo',root,dirs_exist_ok=True)
    checks=[]; failures=[]; timer=QTimer(); started=time.monotonic(); stage=0
    window=MainWindow();window.show()
    def finish(error=None):
        timer.stop()
        if error:failures.append(str(error))
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps({'passed':not failures,'checks':checks,'failures':failures,'profile':window.snapshot.profile if window.snapshot else None},indent=2),encoding='utf-8')
        window.grab().save(str(output.with_suffix('.png')))
        if window.worker:window.cancel()
        else:window.close()
        app.exit(bool(failures))
    def tick():
        nonlocal stage
        if time.monotonic()-started>90:finish('Timed out');return
        if window.worker is not None:return
        if window._pending_error:finish(window._pending_error);return
        try:
            if stage==0:
                for path,source in [('a.js','export const f=()=>1;'),('a.ts','export function f(n:number){return n;}'),('a.tsx','export const A=()=> <div/>;'),('A.java','class A { int f(){return 1;} }'),('A.cs','class A { int F(){return 1;} }'),('a.go','package a\nfunc F() int{return 1}'),('a.rs','pub fn f()->i32{1}')]:
                    assert len(parse_unit(path,source).symbols)>1;checks.append('bundled grammar '+path)
                window.open_path(root)
            elif stage==1:
                assert window.snapshot and 'tsx' in window.snapshot.profile['languages']
                window.analyze(['src/price.mjs:invoiceTotal'])
            elif stage==2:
                assert len(window.lens_view.linked_tests)==2
                assert 'src/Invoice.tsx:Invoice' in window.lens_view.rows
                checks.append('JS transitive tests and TSX caller in native Lens')
                window.open_file('src/Invoice.tsx');window.navigate(0)
                assert window.current_editor()._syntax_language=='tsx'
                assert not window.preview_button.isEnabled()
                checks.append('TSX editor and Python refactoring guard')
                path=root/'src/price.mjs';source=path.read_text(encoding='utf-8')
                path.write_text(source.replace('1 + taxRate','1 + taxRate + 0.1'),encoding='utf-8')
                window.analyze_changes()
            elif stage==3:
                assert 'src/price.mjs:invoiceTotal' in window.report['changes']['seeds']
                assert window.report['changes']['files'][0]['diff']
                checks.append('automatic baseline and JavaScript diff')
                window.navigate(1)
                if shutil.which('node'):
                    tests=list(window.lens_view.linked_tests)
                    assert tests
                    result=run_project_tests(window.snapshot,tests,'',True,20)
                    assert result['returncode']==1,result
                    checks.append('Node selected-file execution detected deliberate failure')
                else:checks.append('Node execution skipped: optional runtime absent')
                finish();return
            stage+=1
        except Exception as exc:finish(repr(exc))
    QMessageBox.warning=lambda *args:None
    timer.timeout.connect(tick);timer.start(100)
    return app.exec()
