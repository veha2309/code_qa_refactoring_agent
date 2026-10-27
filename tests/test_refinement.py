import ast
import json
from pathlib import Path
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QLineEdit
from changelens.core import index_repository,impact_paths
from changelens.local_ai import rewrite_patch
from changelens.lens import map_records,ImpactMap
from changelens.widgets import CodeEditor
from changelens.search import text_matches,search_project
from test_core import write


def app():return QApplication.instance() or QApplication([])


def test_valid_indented_definitions_with_flush_left_multiline_strings(tmp_path):
    source='class Service:\n    """class docs\nflush left documentation\n    """\n    def run(self):\n        value = """data\nflush left value\n        """\n        return value\n'
    write(tmp_path,'service.py',source)
    write(tmp_path,'.python-packages/third_party.py',"raise RuntimeError('must not execute')\ndef broken(\n")
    snap=index_repository(tmp_path)
    assert set(snap.symbols)=={'service.py:Service','service.py:Service.run'}
    from changelens.python_source import symbol_node
    from changelens.workspace import local_names
    from changelens.refactoring import suggestions
    node=symbol_node(snap.symbols['service.py:Service.run'])
    original=ast.parse(source).body[0].body[1]
    assert ast.dump(node)==ast.dump(original)
    assert local_names(snap.symbols['service.py:Service.run'])==['value']
    assert suggestions(snap.symbols['service.py:Service.run'])
    assert not any('Cannot parse' in w for w in snap.warnings)


def test_diamond_graph_preserves_both_routes_and_highlights(tmp_path):
    write(tmp_path,'Auth.tsx','export function Auth(){ return <div/>; }')
    for name in ['Login','Register']:write(tmp_path,name+'.tsx',f"import {{Auth}} from './Auth'; export function {name}(){{ return <Auth/>; }}")
    write(tmp_path,'App.tsx',"import {Login} from './Login'; import {Register} from './Register'; export function App(){ return <><Login/><Register/></>; }")
    snap=index_repository(tmp_path);report={'impact':impact_paths(snap,['Auth.tsx:Auth']),'graph_edges':snap.edges}
    rows,edges,hidden=map_records(report,'Auth.tsx:Auth');assert len(edges)==4
    app();view=ImpactMap();view.set_records(rows,edges,{},'Auth.tsx:Auth');view.select_node('App.tsx:App')
    assert all(node.opacity()==1 for node in view.nodes.values())
    assert all(item.opacity()==1 for item,edge in view.edges)


@pytest.mark.parametrize('path,source,code',[
    ('a.ts','export function total(n: number): number { const x = n + 1; return x; }','function total(n: number): number { return n + 1; }'),
    ('a.tsx','export const Card = ({n}: {n:number}) => <div>{n+1}</div>;','Card = ({n}: {n:number}) => <div>{n + 1}</div>'),
    ('a.js','export default function total(n) { const x = n + 1; return x; }','function total(n) { return n + 1; }'),
    ('A.java','class A { int total(int n) { int x = n + 1; return x; } }','int total(int n) { return n + 1; }'),
    ('A.cs','class A { public int Total(int n) { int x = n + 1; return x; } }','public int Total(int n) { return n + 1; }'),
    ('a.go','package a\nfunc Total(n int) int { x := n + 1; return x }','func Total(n int) int { return n + 1 }'),
    ('a.rs','pub fn total(n: i32) -> i32 { let x = n + 1; x }','pub fn total(n: i32) -> i32 { n + 1 }'),
])
def test_multilanguage_ai_exact_span_keeps_exports_and_surroundings(tmp_path,path,source,code):
    write(tmp_path,path,source);snap=index_repository(tmp_path);symbol=next(s for s in snap.symbols.values() if s.kind=='function')
    patch=rewrite_patch(snap,symbol,json.dumps({'code':code,'explanation':'Remove temporary or normalize spacing.'}))
    assert patch['syntax_validation']=='passed' and patch['tests']=='not run'
    after=patch['files'][0]['after'];assert code in after
    assert (tmp_path/path).read_text(encoding='utf-8')==source
    if source.startswith('export default'):assert after.startswith('export default function')
    elif source.startswith('export const'):assert after.startswith('export const Card')
    elif source.startswith('export'):assert after.startswith('export function')


@pytest.mark.parametrize('code',[
    'function renamed(n: number): number { return n; }',
    'function total(n: string): number { return 1; }',
    'function total(n: number): number { return require("evil"); }',
    'function total(n: number): number { return n; }\nconst extra=1;',
    'function total(n: number): number { return (; }',
])
def test_multilanguage_ai_rejects_signature_dependencies_and_extra_code(tmp_path,code):
    write(tmp_path,'a.ts','export function total(n: number): number { return n + 1; }')
    snap=index_repository(tmp_path)
    with pytest.raises(ValueError):rewrite_patch(snap,snap.symbols['a.ts:total'],json.dumps({'code':code}))


def test_search_counts_utf16_limits_unsaved_buffers_and_literal_query(tmp_path):
    assert text_matches('😀 Auth auth','auth')[0]==[(3,7),(8,12)]
    assert len(text_matches('Auth auth','Auth',True)[0])==1
    assert text_matches('aaaa','a',limit=2)==([(0,1),(1,2)],True)
    write(tmp_path,'a.tsx','// AuthCard')
    write(tmp_path,'b.tsx','// other')
    result=search_project(tmp_path,['a.tsx','b.tsx'],'AuthCard',buffers={'b.tsx':'// AuthCard unsaved'})
    assert len(result['rows'])==2 and {r['path'] for r in result['rows']}=={'a.tsx','b.tsx'}
    assert not search_project(tmp_path,['a.tsx'],'[.*]')['rows']


def test_editor_indentation_tab_stops_block_undo_and_backspace():
    app();editor=CodeEditor();editor.show();editor.setFocus();editor.set_language('a.tsx');editor.set_code('function f() {}');cursor=editor.textCursor();cursor.setPosition(14);editor.setTextCursor(cursor)
    QTest.keyClick(editor,Qt.Key.Key_Return)
    assert editor.toPlainText()=='function f() {\n  \n}'
    QTest.keyClick(editor,Qt.Key.Key_Backspace);assert editor.textCursor().positionInBlock()==0
    editor.set_language('a.py');editor.set_code('if ready: # comment');editor.moveCursor(QTextCursor.MoveOperation.End);QTest.keyClick(editor,Qt.Key.Key_Return)
    assert editor.toPlainText().endswith('\n    ')
    editor.set_code('x = 1\ny = 2\n');cursor=editor.textCursor();cursor.select(QTextCursor.SelectionType.Document);editor.setTextCursor(cursor)
    QTest.keyClick(editor,Qt.Key.Key_Tab);assert editor.toPlainText()=='    x = 1\n    y = 2\n'
    QTest.keyClick(editor,Qt.Key.Key_Backtab);assert editor.toPlainText()=='x = 1\ny = 2\n'
    editor.undo();assert editor.toPlainText()=='    x = 1\n    y = 2\n';editor.close()


def test_automatic_completion_enter_keeps_newline_manual_tab_accepts():
    a=app();editor=CodeEditor();editor.show();editor.activateWindow();editor.setFocus();editor.set_code('mes');editor.moveCursor(QTextCursor.MoveOperation.End);a.processEvents()
    editor.offer_completions(['message'],explicit=False);QTest.keyClick(editor.completer.popup(),Qt.Key.Key_Return);a.processEvents()
    assert editor.toPlainText()=='mes\n'
    editor.set_code('mes');editor.moveCursor(QTextCursor.MoveOperation.End);editor.setFocus();editor.offer_completions(['message'],explicit=True)
    QTest.keyClick(editor.completer.popup(),Qt.Key.Key_Tab);a.processEvents();assert editor.toPlainText()=='message';editor.close()


def test_live_find_no_matches_and_typing_does_not_jump(tmp_path,monkeypatch):
    from changelens.workbench import MainWindow
    from test_lens import wait
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'));monkeypatch.setenv('CHANGELENS_TEST_NO_AI','1')
    root=tmp_path/'project';root.mkdir();write(root,'a.tsx','export const AuthCard = () => <div>AuthCard</div>;')
    a=app();window=MainWindow();window.show();window.open_path(root);wait(a,window);window.navigate(0);window.find_in_file()
    window.find_bar.setText('authcard');window.find_panel.refresh();assert len(window.find_panel.matches)==2 and '2 matches' in window.find_panel.count.text()
    editor=window.current_editor();editor.moveCursor(QTextCursor.MoveOperation.End);editor.insertPlainText(' ');position=editor.textCursor().position();QTest.qWait(180)
    assert editor.textCursor().position()==position
    window.find_bar.setText('missing');window.find_panel.refresh();assert 'No matches' in window.find_panel.count.text()
    window.find_panel.dismiss();editor.document().setModified(False);window.close();a.processEvents()


def test_page_transitions_finish_and_reduced_motion(monkeypatch):
    from changelens.motion import AnimatedStack
    monkeypatch.delenv('CHANGELENS_REDUCE_MOTION',raising=False)
    a=app();a.setProperty('reduceMotion',False);stack=AnimatedStack();stack.addWidget(QLineEdit('one'));second=QLineEdit('two');stack.addWidget(second);stack.show();a.processEvents();stack.setCurrentIndex(1)
    assert stack.overlay is None;QTest.qWait(220);assert stack.overlay is None and stack.currentWidget() is second
    a.setProperty('reduceMotion',True);stack.setCurrentIndex(0);assert stack.overlay is None;a.setProperty('reduceMotion',False);stack.close()


def test_typescript_ai_regeneration_and_reviewed_apply(tmp_path,monkeypatch):
    from changelens.workbench import MainWindow
    from changelens.refactoring import apply_reviewed_patch
    from test_local_ai import settled
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'));monkeypatch.setenv('CHANGELENS_TEST_NO_AI','1')
    root=tmp_path/'project';root.mkdir();source='export function total(n: number): number { const value = n + 1; return value; }\n';target=root/'a.ts';target.write_bytes(source.replace('\n','\r\n').encode())
    a=app();window=MainWindow();window.show();window.open_path(root);settled(a,window);window.assistant_ready=True
    calls=[]
    def assist(*args,**kwargs):
        calls.append(kwargs);return json.dumps({'code':'function total(n: number): number { return n + 1; }','explanation':'Remove temporary.'})
    monkeypatch.setattr(window.local_ai,'assist',assist)
    window.operation.setCurrentIndex(window.operation.findData('ai_rewrite'));assert window.preview_button.isEnabled()
    window.suggest_rewrite();settled(a,window);assert window.patch and window.apply_button.isEnabled() and calls[-1]['language']=='TypeScript'
    window.preview();settled(a,window);assert len(calls)==2
    assert target.read_text(encoding='utf-8')==source
    result=apply_reviewed_patch(window.snapshot,window.patch);assert result['backup']
    assert b'\r\n' in target.read_bytes() and 'export function total' in target.read_text(encoding='utf-8')
    window.close();a.processEvents()


def test_cursor_movement_reuses_symbol_suggestions(tmp_path,monkeypatch):
    import changelens.workbench as workbench
    from test_lens import wait
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'));monkeypatch.setenv('CHANGELENS_TEST_NO_AI','1')
    root=tmp_path/'project';root.mkdir();write(root,'a.py','def alpha(n):\n    return n + 1\n')
    a=app();window=workbench.MainWindow();window.show();window.open_path(root);wait(a,window);calls=[]
    monkeypatch.setattr(workbench,'suggestions',lambda symbol:calls.append(symbol.id) or [])
    window._suggestions_cache={};window._cursor_context_key=None
    for position in range(4,12):
        cursor=window.current_editor().textCursor();cursor.setPosition(position);window.current_editor().setTextCursor(cursor)
    assert len(calls)==1
    window.close();a.processEvents()


def test_changed_lens_keeps_project_focus_and_cross_file_callers(tmp_path,monkeypatch):
    from changelens.workbench import MainWindow
    from changelens.lens import ALL_CHANGES
    from test_lens import wait
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'));monkeypatch.setenv('CHANGELENS_TEST_NO_AI','1')
    root=tmp_path/'project';root.mkdir()
    write(root,'a.py','def alpha(): return 1\ndef untouched(): return 10\n')
    write(root,'b.py','from a import alpha\ndef route(): return alpha()\n')
    write(root,'other.py','def other(): return 2\n')
    a=app();window=MainWindow();window.show();window.open_path(root);wait(a,window)
    write(root,'a.py','def alpha(): return 3\ndef untouched(): return 10\n');write(root,'other.py','def other(): return 4\n')
    window.analyze_changes();wait(a,window);view=window.lens_view
    assert view.focus.findData('a.py:untouched')>=0
    assert view.focus.findData(ALL_CHANGES)>=0
    view.focus.setCurrentIndex(view.focus.findData(ALL_CHANGES));view.focus_changed()
    assert {'a.py:alpha','b.py:route','other.py:other'}<=set(view.rows)
    view.focus.setCurrentIndex(view.focus.findData('a.py:alpha'));view.focus_changed();assert 'b.py:route' in view.rows
    window.close();a.processEvents()


def test_backspace_cancels_pending_automatic_name_popup():
    a=app();editor=CodeEditor();editor.show();editor.setFocus();calls=[];editor.automaticCompletionRequested.connect(lambda:calls.append(True))
    QTest.keyClicks(editor,'ab');QTest.keyClick(editor,Qt.Key.Key_Backspace);QTest.qWait(450)
    assert editor.toPlainText()=='a' and not calls;editor.close();a.processEvents()


def test_escape_discards_pending_model_completion(tmp_path,monkeypatch):
    import time
    from changelens.workbench import MainWindow
    from test_local_ai import settled
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'));monkeypatch.setenv('CHANGELENS_TEST_NO_AI','1')
    root=tmp_path/'project';root.mkdir();write(root,'a.py','def total(n):\n    return n')
    a=app();window=MainWindow();window.show();window.open_path(root);settled(a,window);window.navigate(0);window.ai_ready=True
    editor=window.current_editor();editor.moveCursor(QTextCursor.MoveOperation.End);window.activateWindow();editor.setFocus();a.processEvents()
    def delayed(*args):time.sleep(.15);return {'text':' + 1','seconds':.15,'model':'fixture'}
    monkeypatch.setattr(window.local_ai,'complete',delayed)
    window.request_ai_completion();assert window.ai_worker is not None;QTest.keyClick(editor,Qt.Key.Key_Escape);settled(a,window)
    assert not editor.ghost_text;window.close();a.processEvents()


def test_tabs_and_background_refresh_keep_page_and_tree_stable(tmp_path,monkeypatch):
    from changelens.workbench import MainWindow
    from test_lens import wait
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'));monkeypatch.setenv('CHANGELENS_TEST_NO_AI','1')
    root=tmp_path/'project';root.mkdir();write(root,'a.py','def alpha(): return 1\n');write(root,'b.py','def beta(): return 2\n')
    a=app();window=MainWindow();window.show();window.open_path(root);wait(a,window);window.navigate(0);events=[];window.pages.currentChanged.connect(events.append)
    first=window.explorer.topLevelItem(0);window.open_file('b.py');window.close_document(window.editor_tabs.currentIndex());window.open_file('b.py')
    QTest.qWait(180);assert window.editor_tabs.count()==2 and window.pages.currentIndex()==0 and window.pages.overlay is None
    write(root,'a.py','def alpha(): return 3\n');window.automatic_check();wait(a,window)
    assert window.explorer.topLevelItem(0) is first and window.current_document().path.name=='b.py'
    assert window.pages.currentIndex()==0 and not events and window.updatesEnabled();window.close();a.processEvents()


def test_ai_no_change_keeps_multilanguage_regenerate_available(tmp_path,monkeypatch):
    from changelens.workbench import MainWindow
    from test_local_ai import settled
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'));monkeypatch.setenv('CHANGELENS_TEST_NO_AI','1')
    root=tmp_path/'project';root.mkdir();source='function total(n: number) { return n + 1; }';write(root,'a.ts',source)
    a=app();window=MainWindow();window.show();window.open_path(root);settled(a,window);window.assistant_ready=True;calls=[]
    monkeypatch.setattr(window.local_ai,'assist',lambda *args,**kwargs:calls.append(True) or json.dumps({'code':source}))
    window.suggest_rewrite();settled(a,window)
    assert window.patch is None and window.preview_button.isEnabled() and 'No new improvement returned' in window.refactor_context.text()
    window.preview();settled(a,window);assert len(calls)==2;window.close();a.processEvents()


def test_windows_git_launcher_creates_no_console(tmp_path,monkeypatch):
    import os,subprocess,sys
    import changelens.core as core
    if os.name!='nt':pytest.skip('Windows console regression')
    real_run=subprocess.run
    def probe(command,**kwargs):
        # Exercise the launch options through a real Windows child process,
        # querying its attached console rather than checking only a flag value.
        return real_run([sys.executable,'-c','import ctypes; print(int(bool(ctypes.windll.kernel32.GetConsoleWindow())))'],**kwargs)
    monkeypatch.setattr(core.subprocess,'run',probe)
    assert core.git(tmp_path,'rev-parse','HEAD').strip()=='0'
