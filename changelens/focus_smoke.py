"""Controlled frozen checks for focus UI, edit recovery and model-context guards."""
import json,os,tempfile,time
from pathlib import Path


def run(output):
    os.environ['CHANGELENS_TEST_NO_AI']='1'
    from PySide6.QtCore import QTimer,Qt
    from PySide6.QtTest import QTest
    from PySide6.QtGui import QTextCursor
    from PySide6.QtWidgets import QApplication
    from .core import app_dir
    from .workbench import MainWindow
    from .change_history import versions,restore
    from .edit_review import replace_buffer
    from .local_ai import LocalAI
    app=QApplication.instance() or QApplication([]);folder=tempfile.TemporaryDirectory(prefix='focus-smoke-',dir=app_dir());root=Path(folder.name)
    original='def total(n):\n    return n + 1\n';(root/'calc.py').write_text(original,encoding='utf-8')
    (root/'Auth.tsx').write_text('export function AuthCard(){return <div/>;}',encoding='utf-8')
    (root/'App.tsx').write_text("import {AuthCard} from './Auth';export function App(){return <AuthCard/>;}",encoding='utf-8')
    output.parent.mkdir(parents=True,exist_ok=True);window=MainWindow();window.show();checks=[];pending_restore={};stage=0;started=time.monotonic();timer=QTimer()
    def finish(error=None):
        timer.stop();output.write_text(json.dumps({'passed':not error,'checks':checks,'failures':[str(error)] if error else [],'live_model':False},indent=2),encoding='utf-8')
        if window.worker:window.cancel();window.worker.wait(3000)
        window.close();app.exit(1 if error else 0)
    def tick():
        nonlocal stage
        if time.monotonic()-started>60:finish('Timed out');return
        if window.worker:return
        if window._pending_error:finish(window._pending_error);return
        try:
            if stage==0:window.open_path(root)
            elif stage==1:
                assert window.shell_header.isHidden() and window.options_button.isVisible() and all(b.isVisible() for b in window.workspace_buttons.values()), "Workspace navigation not visible"
                window.workspace_buttons[0].click();assert window.pages.currentIndex()==0 and window.page_action_buttons["Review edits"].isVisible(), "Editor actions not immediately visible";window.workspace_buttons[6].click()
                view=window.lens_view;view.search.setText('AuthCard');assert view.search_results.count()==1;view.activate_search()
                assert view.focus.currentData()=='Auth.tsx:AuthCard' and 'App.tsx:App' in view.rows
                checks.append('visible one-click workspace navigation, routine actions and component search preserve callers')
                window.build_options();window.open_file('calc.py');window.navigate(0)
                editor=window.current_editor();replace_buffer(editor,original.replace('n + 1','n + 2'));editor.update_edit_marks();assert editor.change_marks
                window.review_edits();review=window.edit_review;review.revert_one();assert editor.toPlainText()==original
                editor.undo();assert 'n + 2' in editor.toPlainText();review.close();checks.append('visible gutter edits and one-step hunk revert/undo')
                window.save_current();doc=window.current_document();rows=versions(doc.path);assert rows
                pending_restore.update(editor=editor,path=doc.path,version=rows[0]['id'],digest=doc.digest)
            elif stage==2:
                editor=pending_restore['editor'];fresh=restore(pending_restore['path'],pending_restore['version'],pending_restore['digest'])
                window.documents[editor]=fresh;replace_buffer(editor,fresh.text);editor.document().setModified(False)
                assert fresh.path.read_text(encoding='utf-8')==original;checks.append('saved file history restores source and records a recovery point')
                window.grab().save(str(output.with_name(output.stem+'_editor.png')))
                from .widgets import CodeEditor
                typing=CodeEditor();typing.show();typing.activateWindow();typing.setFocus();typing.set_code('mes');typing.moveCursor(QTextCursor.MoveOperation.End);app.processEvents()
                typing.offer_completions(['message'],explicit=False);QTest.keyClick(typing.completer.popup(),Qt.Key.Key_Return);app.processEvents();assert typing.toPlainText()=='mes\n'
                typing.set_code('mes');typing.moveCursor(QTextCursor.MoveOperation.End);typing.setFocus();typing.offer_completions(['message'],explicit=True);QTest.keyClick(typing.completer.popup(),Qt.Key.Key_Tab);app.processEvents();assert typing.toPlainText()=='message';typing.close()
                checks.append('native completion popup Enter inserts newline and Tab accepts explicit completion')
                client=LocalAI();code='def large(n):\n'+''.join(f'    value_{i} = n + {i}\n' for i in range(500))+'    return value_499\n';old='    value_250 = n + 250'
                def fake(path,payload=None,*args,**kwargs):
                    if path=='/api/show':return {}
                    return {'message':{'content':json.dumps({'edits':[{'old':old,'new':'    value_250 = n + 251'}],'explanation':'Controlled proposal.'})}}
                client.request=fake;answer=json.loads(client.assist(code,'Improve focus',rewrite=True,focus_offset=code.index(old)))
                assert answer['code']==code.replace(old,'    value_250 = n + 251')
                report=client.last_context_report;assert report['estimated_input']+report['reserved_output']<=report['window'] and report['omitted']
                checks.append('large-declaration bounded context and exact edits preserve omitted code (stub model)')
                finish();return
            stage+=1
        except Exception as exc:
            import traceback
            finish(traceback.format_exc())
    timer.timeout.connect(tick);timer.start(100);return app.exec()
