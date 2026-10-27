"""Controlled static fixtures; framework installations are not required."""
import json
import shutil
import sys
from pathlib import Path

import pytest

from changelens.core import index_repository, impact_paths, changed_symbols, ensure_fresh, report_markdown
from changelens.languages import json_config
from changelens.workspace import capture_baseline, baseline_changes, analyze_workspace
from changelens.ranking import rank_tests
from changelens.js_runner import execution_family, javascript_command
from changelens.runner import run_project_tests
from changelens.syntax import parse_unit
from test_core import write, init_git, run_git


def web(root):
    write(root,'package.json',json.dumps({'dependencies':{'react':'19','next':'15'},'devDependencies':{'vitest':'3'}}))
    write(root,'src/math.ts','export function total(n: number) { return n + 1; }\nexport function unrelated() { return 10; }\n')
    write(root,'src/barrel.ts',"export { total as sum } from './math';\n")
    write(root,'src/App.tsx',"import { sum } from './barrel';\nexport const App = () => <div>{sum(2)}</div>;\n")
    write(root,'src/App.test.tsx',"import { test } from 'vitest';\nimport { App } from './App';\ntest('renders', () => { const view = <App />; });\n")
    return index_repository(root)


def test_ts_reexport_jsx_evidence_and_structural_ranking(tmp_path):
    snapshot=web(tmp_path)
    rows={r['symbol']:r for r in impact_paths(snapshot,['src/math.ts:total'])}
    test=next(s.id for s in snapshot.symbols.values() if s.is_test)
    assert rows[test]['path']==['src/math.ts:total','src/App.tsx:App',test]
    assert rows[test]['evidence'][-1]['kind']=='jsx_reference'
    assert 'src/math.ts:unrelated' not in rows
    ranked=rank_tests(snapshot,['src/math.ts:total'])
    assert ranked[0]['recommended'] and ranked[0]['symbol']==test
    assert 'structural ranking' in ranked[0]['method']
    assert {x['name'] for x in snapshot.profile['frameworks']}=={'React','Next.js','Vitest'}


def test_namespace_default_commonjs_and_shadowing(tmp_path):
    write(tmp_path,'a.js','export function calc(){ return 1; }\nexport default calc;')
    write(tmp_path,'b.js',"import value, * as a from './a.js';\nexport function ok(){return value()+a.calc();}\nexport function shadow(value,a){return value()+a.calc();}\nexport function reassigned(){value=other;return value();}")
    write(tmp_path,'c.cjs','function c(){return 2;}\nmodule.exports={c};')
    write(tmp_path,'d.cjs',"const {c: alias} = require('./c.cjs');\nfunction run(){return alias();}")
    snap=index_repository(tmp_path)
    assert sum(e['caller']=='b.js:ok' and e['callee']=='a.js:calc' for e in snap.edges)==2
    assert not any(e['caller'] in {'b.js:shadow','b.js:reassigned'} and e['callee']=='a.js:calc' for e in snap.edges)
    assert any(e['caller']=='d.cjs:run' and e['callee']=='c.cjs:c' for e in snap.edges)


def test_jsonc_alias_and_exclusions(tmp_path):
    config='{"url":"https://example.invalid/*", /* comment */ "compilerOptions":{"paths":{"@/*":["src/*", // trailing comment\n],},},}'
    assert json_config(config)['url']=='https://example.invalid/*'
    write(tmp_path,'tsconfig.json',config)
    write(tmp_path,'src/a.ts','export const calc = () => 1;')
    write(tmp_path,'b.ts',"import {calc} from '@/a';\nfunction run(){return calc();}")
    for folder in ['node_modules','.next','target','obj']:
        write(tmp_path,folder+'/secret.js','throw new Error("never load");')
    snap=index_repository(tmp_path)
    assert any(e['caller']=='b.ts:run' and e['callee']=='src/a.ts:calc' for e in snap.edges)
    assert not any('secret' in p for p in snap.hashes)


def test_ambiguous_modules_syntax_and_dynamic_calls(tmp_path):
    write(tmp_path,'a.js','export function calc(){return 1;}')
    write(tmp_path,'a.ts','export function calc(){return 2;}')
    write(tmp_path,'b.ts',"import {calc} from './a';\nfunction run(callback: any){return calc()+callback();}")
    write(tmp_path,'broken.ts','export const x = ( ;')
    snap=index_repository(tmp_path)
    assert not any(e['caller']=='b.ts:run' and e['callee'].endswith(':calc') for e in snap.edges)
    assert any('Ambiguous' in x for x in snap.warnings)
    assert any('callback' in x for x in snap.warnings)
    assert any('Cannot parse broken.ts' in x for x in snap.warnings)


def test_body_change_baseline_and_config_change(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'))
    root=tmp_path/'project';root.mkdir();snap=web(root);baseline=capture_baseline(snap)
    p=root/'src/math.ts';p.write_text(p.read_text(encoding='utf-8').replace('n + 1','n + 2'),encoding='utf-8')
    changes=baseline_changes(index_repository(root),baseline)
    assert changes['seeds']==['src/math.ts:total']
    write(root,'package.json','{"dependencies":{"react":"20"}}')
    changes=baseline_changes(index_repository(root),baseline)
    assert 'src/App.tsx:<module>' in changes['seeds']
    with pytest.raises(ValueError):ensure_fresh(snap)


def test_git_js_deleted_export_and_additions(tmp_path):
    write(tmp_path,'a.js','export function calc(){return 1;}\n')
    write(tmp_path,'b.js',"import {calc} from './a.js';\nfunction run(){return calc();}\n")
    init_git(tmp_path)
    write(tmp_path,'a.js','export {};\n');run_git(tmp_path,'add','a.js')
    write(tmp_path,'added.ts','export const fresh=()=>1;')
    snap=index_repository(tmp_path);changes=changed_symbols(snap)
    assert 'a.js:calc' in changes['historical_symbols']
    assert any(e['caller']=='b.js:run' and e['callee']=='a.js:calc' for e in changes['historical_edges'])
    assert next(r for r in changes['files'] if r['path']=='added.ts')['status']=='untracked addition'


@pytest.mark.parametrize('path,source,expected',[
    ('A.java','package demo; class A { int calc(){return 1;} @Test void works(){} }',{'A','A.calc','A.works'}),
    ('A.cs','namespace Demo; class A { int Calc(){return 1;} [Fact] public void Works(){} }',{'A','A.Calc','A.Works'}),
    ('a_test.go','package demo\nfunc Calc() int {return 1}\nfunc TestCalc(t *T) {}',{'Calc','TestCalc'}),
    ('a.rs','pub fn calc() -> i32 {1}\n#[test]\nfn works() {}',{'calc','works'}),
])
def test_structural_grammars_and_test_declarations(tmp_path,path,source,expected):
    write(tmp_path,path,source);snap=index_repository(tmp_path)
    assert expected<={s.qualname for s in snap.symbols.values()}
    assert any(s.is_test for s in snap.symbols.values())
    assert any('structural analysis only' in w for w in snap.warnings)
    test=next(s.id for s in snap.symbols.values() if s.is_test)
    assert execution_family(snap,[test]) is None


@pytest.mark.skipif(not shutil.which('node'),reason='Node is optional')
def test_real_node_pass_failure_and_trust(tmp_path):
    write(tmp_path,'calc.mjs','export function calc(){return 1;}')
    write(tmp_path,'calc.test.mjs',"import test from 'node:test';\nimport assert from 'node:assert/strict';\nimport {calc} from './calc.mjs';\ntest('calc',()=>assert.equal(calc(),1));")
    snap=index_repository(tmp_path);tests=[s.id for s in snap.symbols.values() if s.is_test]
    assert len(tests)==1
    with pytest.raises(ValueError,match='trusted'):run_project_tests(snap,tests,'',False)
    result=run_project_tests(snap,tests,'',True,timeout=20)
    assert result['status']=='passed' and result['selection_unit']=='files/filters'
    write(tmp_path,'calc.mjs','export function calc(){return 2;}')
    result=run_project_tests(index_repository(tmp_path),tests,'',True,timeout=20)
    assert result['status']=='failed' and result['returncode']==1
    assert execution_family(snap,['missing']) is None


@pytest.mark.skipif(not shutil.which('node'),reason='Node is optional')
@pytest.mark.parametrize('tool,entry,flag',[('vitest','vitest/vitest.mjs','run'),('@jest/globals','jest/bin/jest.js','--runTestsByPath')])
def test_installed_js_command_only_no_npm(tmp_path,tool,entry,flag):
    write(tmp_path,'a.test.ts',f"import {{test}} from '{tool}';\ntest('x',()=>{{}});")
    write(tmp_path,'node_modules/'+entry,'throw new Error("command fixture never executed");')
    snap=index_repository(tmp_path);ids=[s.id for s in snap.symbols.values() if s.is_test]
    command,cwd,scope,count=javascript_command(snap,ids)
    assert flag in command and count==1 and cwd==tmp_path
    assert not any(x in command for x in ['npm','npx'])
    assert ('filters' in scope)==(tool=='vitest')


def test_multilanguage_report_export(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'))
    root=tmp_path/'project';root.mkdir();web(root)
    snap,report=analyze_workspace(root,['src/math.ts:total'])
    content=report_markdown(report)
    assert 'TypeScript' in content and 'Next.js' in content
    assert 'Tests were not executed' in content


def test_structural_focus_uses_file_scope_not_unproven_symbol_calls(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'))
    root=tmp_path/'project';root.mkdir()
    write(root,'a.go','package demo\nfunc Calc() int {return 1}')
    write(root,'a_test.go','package demo\nfunc TestCalc(t *T) {}')
    snap,report=analyze_workspace(root,['a.go:Calc'])
    assert report['changes']['seeds']==['a.go:<module>']
    assert report['tests'][0]['recommended']
    assert report['tests'][0]['relation']=='Inferred dependency'
    assert any('containing file/module' in w for w in report['warnings'])


def test_cycles_and_unicode_imports(tmp_path):
    write(tmp_path,'परीक्षण space/café.ts',"import {b} from './b';\nexport function a(){return b();}")
    write(tmp_path,'परीक्षण space/b.ts',"import {a} from './café';\nexport function b(){return a();}")
    snap=index_repository(tmp_path)
    rows=impact_paths(snap,['परीक्षण space/café.ts:a'])
    assert len(rows)==2


def test_baseline_migration_keeps_python_history(tmp_path,monkeypatch):
    import sqlite3
    from changelens.core import app_dir
    from changelens.workspace import automatic_comparison,load_baseline
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'))
    root=tmp_path/'project';root.mkdir();write(root,'a.py','x=1\n')
    snap=index_repository(root);record=capture_baseline(snap);record.pop('schema')
    with sqlite3.connect(app_dir()/'cache.sqlite3') as db:db.execute('UPDATE baselines SET payload=? WHERE root=?',(json.dumps(record),snap.root))
    write(root,'a.py','x=2\n');write(root,'a.js','export const run=()=>1;')
    current=index_repository(root);automatic_comparison(current);migrated=load_baseline(snap.root)
    assert migrated['schema']==2 and migrated['files']['a.py'].splitlines()==['x=1']
    assert migrated['files']['a.js']=='export const run=()=>1;'


def test_multilanguage_native_editor_staleness_and_guards(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'));monkeypatch.setenv('CHANGELENS_TEST_NO_AI','1')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QTextCursor
    from changelens.workbench import MainWindow
    from test_lens import wait
    root=tmp_path/'project';root.mkdir();web(root)
    app=QApplication.instance() or QApplication([]);window=MainWindow();window.show()
    window.open_path(root);wait(app,window)
    window.open_file('src/App.tsx');window.navigate(0)
    assert window.current_editor()._syntax_language=='tsx'
    assert not window.preview_button.isEnabled()
    window.analyze(['src/math.ts:total']);wait(app,window)
    assert window.validate_button.isEnabled()
    editor=window.current_editor();editor.moveCursor(QTextCursor.MoveOperation.End);editor.insertPlainText('\n// unsaved\n')
    assert window.report_stale and not window.validate_button.isEnabled()
    editor.document().setModified(False);window.close();app.processEvents()


@pytest.mark.skipif(not shutil.which('node'),reason='Node is optional')
def test_mixed_javascript_runners_rejected(tmp_path):
    write(tmp_path,'node.test.mjs',"import test from 'node:test'; test('node',()=>{});")
    write(tmp_path,'vitest.test.mjs',"import {test} from 'vitest'; test('vitest',()=>{});")
    snap=index_repository(tmp_path);ids=[s.id for s in snap.symbols.values() if s.is_test]
    with pytest.raises(ValueError,match='one test runner'):javascript_command(snap,ids)
