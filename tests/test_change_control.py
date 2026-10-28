import json
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextCursor
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from changelens.core import index_repository
from changelens.workspace import Document
from changelens.change_history import versions,restore
from changelens.local_ai import LocalAI,rewrite_patch
from changelens.model_context import snippet_edits
from test_core import write


def test_history_restore_conflicts_unicode_and_recovery(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'))
    path=tmp_path/'source ü.py';original=bytes.fromhex('efbbbf')+b'value = 1'+bytes([13,10]);path.write_bytes(original)
    doc=Document(path);doc.save('value = 2'+chr(10));rows=versions(path);assert len(rows)==1
    with pytest.raises(ValueError):restore(path,rows[0]['id'],'stale')
    restored=restore(path,rows[0]['id'],doc.digest)
    assert restored.raw==original and len(versions(path))==2
    restore(path,versions(path)[0]['id'],restored.digest)
    assert b'value = 2' in path.read_bytes()


def test_revert_hunk_is_one_undo_step_and_saved_markers_persist(tmp_path,monkeypatch):
    from changelens.workbench import MainWindow
    from test_lens import wait
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'));monkeypatch.setenv('CHANGELENS_TEST_NO_AI','1')
    root=tmp_path/'p';root.mkdir();write(root,'a.py','a = 1\nb = 2\n')
    app=QApplication.instance() or QApplication([]);w=MainWindow();w.show();w.open_path(root);wait(app,w);w.navigate(0)
    editor=w.current_editor();editor.moveCursor(QTextCursor.MoveOperation.End);editor.insertPlainText('c = 3\n');editor.update_edit_marks();assert editor.change_marks
    w.save_current();assert editor.opening_text=='a = 1\nb = 2\n'
    w.review_edits();dialog=w.edit_review;assert dialog.entries
    dialog.revert_one();assert editor.toPlainText()==editor.opening_text
    editor.undo();assert editor.toPlainText().endswith('c = 3\n')
    unchanged=editor.toPlainText();dialog.revert_all();assert editor.toPlainText()==unchanged and 'Refresh' in dialog.note.text()
    dialog.close();editor.document().setModified(False);w.close();app.processEvents()


def test_compact_shell_and_component_search(tmp_path,monkeypatch):
    from changelens.workbench import MainWindow
    from test_lens import wait
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'));monkeypatch.setenv('CHANGELENS_TEST_NO_AI','1')
    root=tmp_path/'p';root.mkdir();write(root,'auth.tsx','export function AuthCard(){ return <div/>; }')
    write(root,'app.tsx',"import {AuthCard} from './auth'; export function Login(){ return <AuthCard/>; }")
    app=QApplication.instance() or QApplication([]);w=MainWindow();w.show();w.open_path(root);wait(app,w)
    assert w.shell_header.isHidden() and w.nav.isHidden() and w.options_button.isVisible()
    w.activateWindow();w.setFocus();app.processEvents();QTest.keyClick(w,Qt.Key.Key_P,Qt.KeyboardModifier.ControlModifier);app.processEvents()
    assert w.picker.isVisible();w.picker.close()
    lens=w.lens_view;lens.search.setText('authcard');assert lens.search_results.count()==1
    lens.activate_search();assert lens.focus.currentData()=='auth.tsx:AuthCard' and 'app.tsx:Login' in lens.rows
    lens.search.setText('not found');assert lens.search_count.text()=='No matches'
    w.build_options();assert w.options_menu.actions()
    w.navigate(8);app.processEvents();wait(app,w)
    assert w.architecture_view.canvas.toolbar.isVisible()
    assert w.workspace_buttons[8].isChecked() and all(b.isVisible() for b in w.workspace_buttons.values())
    QTest.mouseClick(w.workspace_buttons[0],Qt.MouseButton.LeftButton);app.processEvents()
    assert w.pages.currentIndex()==0 and w.page_action_buttons['Save'].isVisible() and w.page_action_buttons['Review edits'].isVisible()
    w.close();app.processEvents()


def test_large_code_uses_visible_exact_edits_and_bounded_payload(monkeypatch):
    client=LocalAI();calls=[]
    code='def process(n):\n'+''.join(f'    value_{i} = n + {i}\n' for i in range(800))+'    return value_799\n'
    target='    value_400 = n + 400'
    def request(path,payload=None,*args,**kwargs):
        calls.append((path,payload))
        if path=='/api/show':return {'model_info':{'qwen.context_length':32768}}
        return {'message':{'content':json.dumps({'edits':[{'old':target,'new':'    value_400 = n + 401'}],'explanation':'A proposed change for review.'})}}
    monkeypatch.setattr(client,'request',request)
    answer=json.loads(client.assist(code,'Improve the focused code',rewrite=True,focus_offset=code.index(target)))
    assert 'value_400 = n + 401' in answer['code'] and 'value_799' in answer['code']
    report=client.last_context_report;assert report['omitted'] and report['estimated_input']+report['reserved_output']<=report['window']
    prompt=calls[-1][1]['messages'][1]['content'];assert target in prompt and 'value_799' not in prompt
    with pytest.raises(ValueError):snippet_edits(code,target,[{'old':'    value_799 = n + 799','new':'x'}])
    with pytest.raises(ValueError):snippet_edits('same value\nsame value','same value',[{'old':'same value','new':'other'}])


def test_snippet_rewrite_preserves_omitted_multiline_literal(tmp_path):
    source='class Service:\n    def run(self):\n        value = """data\nflush left content\n        """\n        result = 1 + 2\n        return result\n'
    write(tmp_path,'a.py',source);snap=index_repository(tmp_path);symbol=snap.symbols['a.py:Service.run']
    result=rewrite_patch(snap,symbol,json.dumps({'code':'ignored','_context_edits':[{'old':'result = 1 + 2','new':'result = 3'}]}))
    after=result['files'][0]['after'];assert 'flush left content\n        """' in after and 'result = 3' in after
    assert (tmp_path/'a.py').read_text()==source


def test_truncated_response_rejected(monkeypatch):
    client=LocalAI()
    monkeypatch.setattr(client,'request',lambda path,payload=None,*a,**kw:{} if path=='/api/show' else {'done_reason':'length','message':{'content':'partial'}})
    with pytest.raises(ValueError,match='output limit'):client.assist('def x(): return 1','Improve',rewrite=True)


def test_large_foreign_snippet_rewrite_preserves_rest(tmp_path):
    source='export function calculate(n: number): number {\n'+''.join(f'  const value_{i} = n + {i};\n' for i in range(500))+'  return value_499;\n}\n'
    write(tmp_path,'a.ts',source);snap=index_repository(tmp_path);symbol=snap.symbols['a.ts:calculate']
    result=rewrite_patch(snap,symbol,json.dumps({'code':'ignored','_context_edits':[{'old':'const value_250 = n + 250;','new':'const value_250 = n + 251;'}]}))
    assert result['files'][0]['after']==source.replace('const value_250 = n + 250;','const value_250 = n + 251;')


def test_older_refactoring_backups_are_restorable(tmp_path,monkeypatch):
    from changelens.core import app_dir
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'))
    root=tmp_path/'project';root.mkdir();path=root/'a.py';path.write_text('value = 2\n')
    backup=app_dir()/'backups'/'earlier';backup.mkdir(parents=True);(backup/'0.original').write_bytes(b'value = 1\n')
    (backup/'manifest.json').write_text(json.dumps({'root':str(root),'files':[{'path':'a.py','backup':'0.original','after_sha256':'unused'}]}))
    doc=Document(path);saved=versions(path);assert saved[0]['origin']=='refactoring backup'
    restore(path,saved[0]['id'],doc.digest);assert path.read_text()=='value = 1\n'


def test_editor_marks_existing_git_changes_without_resetting_index(tmp_path,monkeypatch):
    from test_core import init_git,run_git
    from test_lens import wait
    from changelens.workbench import MainWindow
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'));monkeypatch.setenv('CHANGELENS_TEST_NO_AI','1')
    root=tmp_path/'repo';root.mkdir();write(root,'a.py','value = 1\n');init_git(root)
    write(root,'a.py','value = 2\n');run_git(root,'add','a.py')
    app=QApplication.instance() or QApplication([]);w=MainWindow();w.open_path(root);wait(app,w);w.navigate(0)
    editor=w.current_editor();assert editor.opening_text=='value = 2\n' and editor.change_base_text=='value = 1\n' and editor.change_marks
    w.review_edits();dialog=w.edit_review;dialog.revert_all();assert editor.toPlainText()=='value = 1\n'
    assert run_git(root,'show',':a.py').stdout.decode()=='value = 2\n'
    dialog.close();editor.document().setModified(False);w.close();app.processEvents()
