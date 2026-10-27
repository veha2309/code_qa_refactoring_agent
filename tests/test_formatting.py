import ast
import json
from threading import Event

import pytest

from changelens.core import Cancelled
from changelens.formatting import format_document,formatter_for


def test_python_format_equivalence_idempotence_and_comments():
    source='# keep this comment\ndef total( a,b ):\n return a+b # amount\n'
    result=format_document('total.py',source)
    assert result['changed'] and result['engine']=='Black'
    assert ast.dump(ast.parse(result['after']))==ast.dump(ast.parse(source))
    assert '# keep this comment' in result['after'] and '# amount' in result['after']
    assert not format_document('total.py',result['after'])['changed']


@pytest.mark.parametrize('path,source',[
    ('a.js','export function total(a,b){return a+b}'),
    ('a.jsx','export const A=()=> <div value={1+2}>Hello</div>'),
    ('a.ts','export const total=(a:number,b:number)=>a+b'),
    ('a.tsx','export const A=({n}:{n:number})=> <div>{n+1}</div>'),
    ('package.json','{"a":1,"b":[1,2]}'),
    ('tsconfig.json','{// aliases\n"compilerOptions":{"strict":true,},}'),
])
def test_web_formats_offline_and_is_idempotent(path,source):
    from changelens.syntax import parse_unit
    result=format_document(path,source)
    assert result['changed'] and result['engine']=='Prettier'
    assert not format_document(path,result['after'])['changed']
    if path.endswith(('.js','.jsx','.ts','.tsx')):parse_unit(path,result['after'])
    if path=='package.json':assert json.loads(result['after'])==json.loads(source)


def test_project_plugins_and_environment_are_not_loaded(tmp_path,monkeypatch):
    marker=tmp_path/'executed.txt'
    script="require('node:fs').writeFileSync("+json.dumps(str(marker)) + ",'executed');"
    plugin=tmp_path/'malicious.cjs';plugin.write_text(script,encoding='utf-8')
    (tmp_path/'prettier.config.cjs').write_text(script,encoding='utf-8')
    monkeypatch.setenv('NODE_OPTIONS','--require '+str(plugin))
    monkeypatch.setenv('NODE_PATH',str(tmp_path))
    result=format_document(tmp_path/'a.js','const answer=1+2')
    assert '1 + 2' in result['after'] and not marker.exists()


def test_reject_invalid_unsupported_oversize_and_cancel():
    assert formatter_for('A.java') is None
    for path,source in [('a.py','def broken('),('a.ts','const a = ( ;'),('a.json','{"a":}')]:
        with pytest.raises(ValueError):format_document(path,source)
    with pytest.raises(ValueError,match='currently supports'):format_document('a.rs','fn a(){}')
    with pytest.raises(ValueError,match='2 MB'):format_document('a.js','x'*2_000_001)
    cancel=Event();cancel.set()
    with pytest.raises(Cancelled):format_document('a.py','x=1',cancel)


def test_preview_applies_buffer_only_single_undo_and_stale_guard(tmp_path,monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen');monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'));monkeypatch.setenv('CHANGELENS_TEST_NO_AI','1')
    from PySide6.QtWidgets import QApplication
    from changelens.workbench import MainWindow
    from test_lens import wait
    from changelens.format_ui import apply_to_editor
    root=tmp_path/'project';root.mkdir();target=root/'a.py';original='def add( a,b ):\n return a+b\n';target.write_text(original,encoding='utf-8')
    app=QApplication.instance() or QApplication([]);window=MainWindow();window.show();window.open_path(root);wait(app,window);window.navigate(0)
    assert window.format_button.isEnabled()
    editor=window.current_editor();window.format_current();wait(app,window)
    preview=window.format_preview;assert preview.isVisible()
    preview.apply_button.click();app.processEvents()
    assert editor.toPlainText()!='' and 'def add(a, b):' in editor.toPlainText()
    assert target.read_text(encoding='utf-8')==original and editor.document().isModified()
    assert window.report_stale
    editor.undo();assert editor.toPlainText()==original
    result=format_document('a.py',original);editor.insertPlainText('# edited\n')
    with pytest.raises(ValueError,match='changed after'):apply_to_editor(editor,result)
    editor.document().setModified(False);window.close();app.processEvents()
