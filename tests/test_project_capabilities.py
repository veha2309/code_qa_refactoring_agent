import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import pytest
from PySide6.QtWidgets import QApplication
from changelens.core import index_repository
from changelens.architecture import review_architecture
from changelens.feature_flows import design_model


def put(root,path,source):
    target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(source,encoding='utf-8')


def test_next_app_router_and_fastapi_flask_are_source_backed(tmp_path):
    put(tmp_path,'package.json','{"dependencies":{"next":"15","react":"19"}}')
    put(tmp_path,'app/api/items/[id]/route.ts',"import {NextResponse} from 'next/server';export async function GET(){return NextResponse.json({items:[]},{status:201});}")
    put(tmp_path,'app/page.tsx',"export async function Screen(){const result=await fetch('/api/items/123');return <div/>;}")
    put(tmp_path,'service.py',"from fastapi import FastAPI\napp=FastAPI()\n@app.post('/ingest')\ndef ingest():\n return {'ok': True}\n")
    put(tmp_path,'flask_app.py',"from flask import Flask,jsonify\napp=Flask(__name__)\n@app.route('/status', methods=['GET','POST'])\ndef status():\n return jsonify(ok=True), 202\n")
    report=review_architecture(index_repository(tmp_path));data=report['feature_flows']
    assert {(r['method'],r['endpoint']) for r in data['routes']}=={('GET','/api/items/:id'),('POST','/ingest'),('GET','/status'),('POST','/status')}
    flow=data['flows'][0];assert flow['matches'][0]['framework']=='Next.js App Router'
    assert flow['matches'][0]['handler_detail']['responses'][0]['status']=='201'
    assert flow['matches'][0]['handler_detail']['responses'][0]['fields']==['items']
    model=design_model(report);assert any(n['kind']=='Registered HTTP routes' for n in model['nodes'])


def test_non_next_route_filename_does_not_invent_registration(tmp_path):
    put(tmp_path,'app/api/demo/route.ts','export function GET(){return 1;}')
    report=review_architecture(index_repository(tmp_path));assert report['feature_flows']['routes']==[]


def test_server_only_project_can_open_implementation_and_pan_on_cards(tmp_path,monkeypatch):
    from changelens.architecture_ui import ArchitectureView
    from test_design_interactions import drag_view,positions
    from PySide6.QtCore import QPoint
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'))
    put(tmp_path,'api.py',"from fastapi import FastAPI\napp=FastAPI()\n@app.get('/health')\ndef health(): return {'ok': True}\n")
    report=review_architecture(index_repository(tmp_path));app=QApplication.instance() or QApplication([]);view=ArchitectureView();view.resize(1500,950);view.set_report(report);view.show();app.processEvents()
    assert view.tabs.currentWidget() is view.flows and view.flows.features.count()==1
    view.flows.features.setCurrentRow(0);app.processEvents();canvas=view.flows.canvas
    assert any(n['kind']=='Server entry point' for n in canvas.model['nodes'])
    assert canvas.pan_button.isChecked()
    node=next(iter(canvas.nodes.values()));canvas.view.centerOn(node.sceneBoundingRect().center());app.processEvents()
    before=positions(canvas);center=canvas.view.mapToScene(canvas.view.viewport().rect().center())
    point=canvas.view.mapFromScene(node.sceneBoundingRect().center());drag_view(canvas,app,point,QPoint(80,50))
    assert canvas.view.mapToScene(canvas.view.viewport().rect().center())!=center and positions(canvas)==before and canvas.history.count()==0
    view.close();app.processEvents()


def test_installed_review_model_connects_and_resumes_without_loading_completion(tmp_path,monkeypatch):
    from changelens.workbench import MainWindow
    from changelens.local_ai import ASSISTANT_MODEL
    from test_local_ai import settled
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'));monkeypatch.setenv('CHANGELENS_TEST_NO_AI','1')
    root=tmp_path/'p';root.mkdir()
    put(root,'limits.ts','export const LIMIT: number = 36;')
    put(root,'calc.ts',"import {LIMIT as CAP} from './limits';\nexport function calc(n: number){ return Math.min(n, CAP); }")
    app=QApplication.instance() or QApplication([]);w=MainWindow();w.open_path(root);settled(app,w)
    monkeypatch.setattr(w.local_ai,'models',lambda cancel:{ASSISTANT_MODEL})
    def no_warmup(*args):raise AssertionError('Discovering review availability must not load the completion model')
    monkeypatch.setattr(w.local_ai,'warm_up',no_warmup)
    w.open_file('calc.ts',2)
    def assist(code,instruction,context,**kwargs):
        assert 'Math.min(n, CAP)' in code
        assert 'limits.ts:1' in context and 'LIMIT: number = 36' in context
        return json.dumps({'summary':'Review this calculation.','uncertainty':'Interpretation.','verification':[]})
    monkeypatch.setattr(w.local_ai,'assist',assist)
    w.review_code();settled(app,w)
    assert w.assistant_ready and not w.ai_ready and w.last_model_review['language']=='TypeScript'
    assert w.pending_model_action is None
    w.close();app.processEvents()


@pytest.mark.parametrize('files,focus,definition', [
    ({'workflow.py':'from limits import LIMIT as CAP\ndef page(n):\n    return min(n, CAP)\n',
      'limits.py':'LIMIT = 36\n'}, 'workflow.py', 'limits.py'),
    ({'workflow.cjs':"const { LIMIT: CAP } = require('./limits.cjs');\nfunction page(n) { return Math.min(n, CAP); }",
      'limits.cjs':'const LIMIT = 36;\nmodule.exports = { LIMIT };'}, 'workflow.cjs', 'limits.cjs'),
    ({'workflow.tsx':"import { LIMIT as CAP } from './limits';\nexport function page(n: number) { return Math.min(n, CAP); }",
      'limits.ts':'export const LIMIT: number = 36;'}, 'workflow.tsx', 'limits.ts'),
    ({'Workflow.java':'class Workflow { static int page(int n) { return Math.min(n, Limits.LIMIT); } }',
      'Limits.java':'class Limits { static final int LIMIT = 36; }'}, 'Workflow.java', 'Limits.java'),
    ({'Workflow.cs':'namespace Demo;\nclass Workflow { static int page(int n) { return n < Limits.LIMIT ? n : Limits.LIMIT; } }',
      'Limits.cs':'namespace Demo;\nclass Limits { public const int LIMIT = 36; }'}, 'Workflow.cs', 'Limits.cs'),
    ({'workflow.go':'package demo\nfunc page(n int) int { return min(n, LIMIT) }',
      'limits.go':'package demo\nconst LIMIT = 36'}, 'workflow.go', 'limits.go'),
    ({'workflow.rs':'mod limits;\nfn page(n: i32) -> i32 { n.min(limits::LIMIT) }',
      'limits.rs':'pub const LIMIT: i32 = 36;'}, 'workflow.rs', 'limits.rs'),
    ({'workflow.dart':"import 'limits.dart' as caps;\nint page(int n) => n < caps.LIMIT ? n : caps.LIMIT;",
      'limits.dart':'const int LIMIT = 36;'}, 'workflow.dart', 'limits.dart'),
])
def test_focused_model_context_includes_cross_file_data(tmp_path,files,focus,definition):
    from changelens.model_context import estimate_tokens,related_context
    for path,source in files.items():
        put(tmp_path,path,source)
    snapshot=index_repository(tmp_path)
    symbol=next(row for row in snapshot.symbols.values() if row.path==focus and row.name=='page')
    context=related_context(snapshot,symbol,budget=256)
    assert definition+':' in context and 'LIMIT' in context and '= 36' in context
    assert estimate_tokens(context)<=256


def test_startup_discovers_existing_models_and_respects_explicit_disable(tmp_path,monkeypatch):
    from changelens.workbench import MainWindow
    from changelens.core import app_dir
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'));monkeypatch.setenv('CHANGELENS_TEST_NO_AI','1')
    app=QApplication.instance() or QApplication([]);w=MainWindow();calls=[]
    monkeypatch.setattr(w,'connect_ai',lambda:calls.append('discovered'))
    monkeypatch.delenv('CHANGELENS_TEST_NO_AI');w.initialize_ai();app.processEvents();assert calls==['discovered']
    (app_dir()/'local-ai.json').write_text('{"enabled":false}',encoding='utf-8')
    w.initialize_ai();app.processEvents();assert calls==['discovered']
    w.close();app.processEvents()


SOURCES=[
    ('a.py','def calc(n):\n    return n + 1\n'),
    ('a.js','export function calc(n){return n + 1;}'),
    ('a.ts','export function calc(n: number): number {return n + 1;}'),
    ('a.tsx','export function calc(n: number): number {return n + 1;}'),
    ('a.dart','int calc(int n) {return n + 1;}'),
    ('A.java','class A { int calc(int n) {return n + 1;} }'),
    ('A.cs','class A { int calc(int n) {return n + 1;} }'),
    ('a.go','package demo\nfunc calc(n int) int {return n + 1}'),
    ('a.rs','fn calc(n: i32) -> i32 {n + 1}')]


@pytest.mark.parametrize('path,source',SOURCES)
def test_language_neutral_overview_findings_and_rewrite_ui(tmp_path,monkeypatch,path,source):
    from changelens.workbench import MainWindow
    from changelens.languages import language_for,NAMES,structural_refactoring
    from test_lens import wait
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'));monkeypatch.setenv('CHANGELENS_TEST_NO_AI','1')
    root=tmp_path/'project';root.mkdir();put(root,path,source)
    snapshot=index_repository(root);symbol=next(s for s in snapshot.symbols.values() if s.name=='calc')
    report=review_architecture(snapshot);model=design_model(report)
    assert any(n['kind']=='Source modules' for n in model['nodes'])
    app=QApplication.instance() or QApplication([]);w=MainWindow();w.open_path(root);wait(app,w);w.open_file(path,symbol.start);w.assistant_ready=True
    calls=[]
    def assist(code,instruction,*args,**kwargs):
        calls.append(kwargs['language'])
        if kwargs.get('rewrite'):return json.dumps({'code':code.replace('n + 1','(n + 1)'),'explanation':'Group the expression.'})
        return json.dumps({'summary':'Check the supplied calculation.','uncertainty':'Model interpretation only.','verification':['Inspect boundary inputs.']})
    monkeypatch.setattr(w.local_ai,'assist',assist)
    if not structural_refactoring(path):
        w.navigate(4);assert w.operation.currentData()=='ai_rewrite' and not w.operation.model().item(0).isEnabled()
    w.review_code()
    from test_local_ai import settled
    settled(app,w);assert getattr(w,'last_model_review',{}).get('language')==NAMES[language_for(path)],(w.ai_status.text(),w.status.text(),calls)
    w.architecture_snapshot=snapshot;w.architecture_view.set_report(report);w.review_project_model();settled(app,w)
    assert w.last_model_review['scope']=='sampled project sources' and w.last_model_review['sources'][0]['path']==path
    w.suggest_rewrite();settled(app,w)
    assert w.patch and w.patch['syntax_validation']=='passed',(path,w.status.text())
    assert calls==[NAMES[language_for(path)]]*3
    assert (root/path).read_text()==source
    w.close();app.processEvents()
