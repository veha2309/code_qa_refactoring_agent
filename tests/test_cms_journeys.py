import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
from PySide6.QtWidgets import QApplication
from changelens.core import index_repository
from changelens.feature_flows import analyze_flows,design_model
from changelens.flow_drafts import rebase_draft
from changelens.flow_evidence import affected_features


def fixture(root):
    files={
        'api.js':"import axios from 'axios';export async function load(id){const response=await axios.get(`/calendar/${id}`);return response.data;}",
        'index.js':"export {load as dates} from './api.js';",
        'Screen.jsx':"import {dates} from './index.js';import {useState} from 'react';export function Screen(){const [items,setItems]=useState([]);async function refresh(){const data=await dates(id);setItems(data);}return <main>{items.map(x=><p>{x.date}</p>)}</main>;}",
        'app.js':"import express from 'express';import {calendar} from './controller.js';const app=express();app.get('/calendar/:id',auth,calendar);",
        'controller.js':"import {read} from './service.js';export async function calendar(req,res){const data=await read(req.params.id);return res.status(200).json({data});}",
        'service.js':"import Calendar from './model.js';export async function read(id){return Calendar.find({InstituteId:id});}",
        'model.js':'export default {};'
    }
    for path,source in files.items():(root/path).write_text(source,encoding='utf-8')
    return index_repository(root)


def test_reexport_service_state_helpers_and_typed_evidence(tmp_path):
    snapshot=fixture(tmp_path);data=analyze_flows(snapshot);flow=data['flows'][0]
    assert data['version']==2 and data['snapshot_id']==snapshot.id
    assert flow['screen']=='Screen' and flow['updates'][0]['state']=='items'
    assert flow['updates'][0]['renders'][0]['state']=='items'
    assert flow['matches'][0]['service_helpers'][0]['data'][0]['operation']=='Calendar.find'
    assert {'HTTP candidate','call','data access','state update','render'}<={r['kind'] for r in flow['relationships']}
    assert all(r['evidence'][0]['line']>0 for r in flow['relationships'])
    assert next(r for r in flow['relationships'] if r['kind']=='HTTP candidate')['classification']=='path match'
    changed={'seeds':['service']};locations={'service':{'path':'service.js','start':1,'end':1}}
    assert affected_features(data,changed,locations)[0]['screen']=='Screen'


def test_cache_rejoins_deleted_and_restored_imports(tmp_path):
    snapshot=fixture(tmp_path);first=analyze_flows(snapshot);second=analyze_flows(snapshot)
    assert second['cache_hits']==len(snapshot.hashes)
    (tmp_path/'service.js').unlink();third=analyze_flows(index_repository(tmp_path))
    assert not third['flows'][0]['matches'][0]['service_helpers']
    assert third['flows'][0]['gaps']
    fixture(tmp_path);assert analyze_flows(index_repository(tmp_path))['flows'][0]['matches'][0]['service_helpers']


def test_transformed_wrapper_does_not_claim_state_propagation(tmp_path):
    fixture(tmp_path);p=tmp_path/'api.js';p.write_text(p.read_text().replace('return response.data','return transform(response.data)'))
    flow=analyze_flows(index_repository(tmp_path))['flows'][0]
    assert flow['updates']==[] and any('transformation' in g for g in flow['gaps'])


def test_flow_navigation_refresh_and_draft_rebase(tmp_path):
    from changelens.flow_ui import FeatureFlows
    app=QApplication.instance() or QApplication([])
    snapshot=fixture(tmp_path);data=analyze_flows(snapshot)
    report={'project':str(tmp_path),'snapshot_id':snapshot.id,'feature_flows':data}
    view=FeatureFlows();view.set_report(report);view.search.setText('screen')
    assert view.features.count()==1 and '1 matching' in view.results.text()
    view.features.setCurrentRow(0);view.show_detail();assert view.evidence.topLevelItemCount()>0
    view.travel(-1);assert not view.detail;view.travel(1);assert view.detail
    selected=view.current_flow;view.set_report(report);assert view.current_flow==selected and view.detail
    base=design_model(report,data['flows'][0]);draft=deepcopy(base);draft['nodes'][0]['title']='My screen'
    fresh=deepcopy(base);fresh['snapshot_id']='new';fresh['nodes'][0]['operations'].append('Changed source fact')
    rebased=rebase_draft(base,draft,fresh)
    assert rebased['nodes'][0]['title']=='My screen' and 'Changed source fact' in rebased['nodes'][0]['operations']
    assert rebased['draft_overlays'][0]['needs_review']
    view.close()


def test_feature_identity_survives_line_insertions_and_cache_model_deletion(tmp_path):
    fixture(tmp_path);before=analyze_flows(index_repository(tmp_path))['flows'][0]
    p=tmp_path/'api.js';p.write_text('\n\n'+p.read_text())
    after=analyze_flows(index_repository(tmp_path))['flows'][0]
    assert before['id']==after['id'] and after['line']==before['line']+2
    assert [s['id'] for s in before['steps']]==[s['id'] for s in after['steps']]
    (tmp_path/'model.js').unlink()
    after=analyze_flows(index_repository(tmp_path))['flows'][0]
    assert after['matches'][0]['service_helpers'][0]['data']==[]


def test_cms_proposal_apply_revert_and_context_budget(tmp_path,monkeypatch):
    import json
    from changelens.local_ai import rewrite_patch
    from changelens.refactoring import apply_reviewed_patch
    from changelens.change_history import restore,versions
    from changelens.workspace import Document,analyze_workspace
    from changelens.model_context import related_context,estimate_tokens
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'))
    root=tmp_path/'project';root.mkdir();snapshot=fixture(root)
    path=root/'service.js';original=path.read_bytes();symbol=next(s for s in snapshot.symbols.values() if s.path=='service.js' and s.name=='read')
    context=related_context(snapshot,symbol,analyze_flows(snapshot),budget=400)
    assert estimate_tokens(context)<=400 and 'Omitted' in context and 'source' in context
    proposal=rewrite_patch(snapshot,symbol,json.dumps({'code':symbol.source.replace('return Calendar.find','const result = Calendar.find').replace(';}', '; return result;}'),'explanation':'Name the result.'}))
    assert path.read_bytes()==original
    apply_reviewed_patch(snapshot,proposal)
    current,report=analyze_workspace(root,seeds={'path':'service.js','line':1})
    assert report['affected_features'][0]['screen']=='Screen'
    doc=Document(path);restore(path,versions(path)[0]['id'],doc.digest)
    assert path.read_bytes()==original


def test_rapid_repository_switch_discards_old_worker(tmp_path,monkeypatch):
    from changelens.workbench import MainWindow
    from test_lens import wait
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'));monkeypatch.setenv('CHANGELENS_TEST_NO_AI','1')
    a=tmp_path/'a';b=tmp_path/'b';a.mkdir();b.mkdir();fixture(a);(b/'other.py').write_text('def other(): return 1\n')
    app=QApplication.instance() or QApplication([]);w=MainWindow();w.open_path(a);w.open_path(b);wait(app,w)
    assert w.snapshot.root==str(b.resolve()) and set(w.snapshot.hashes)=={'other.py'}
    w.close();app.processEvents()


def test_annotation_store_reset_and_workspace_isolation(tmp_path,monkeypatch):
    from changelens.flow_drafts import draft_store
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'))
    snapshot=fixture(tmp_path);data=analyze_flows(snapshot)
    model=design_model({'project':'demo','snapshot_id':snapshot.id,'feature_flows':data},data['flows'][0]);draft=deepcopy(model);draft['nodes'][0]['title']='My note'
    draft_store('workspace-a','feature',model,draft)
    assert draft_store('workspace-a','feature')['draft']['nodes'][0]['title']=='My note'
    assert draft_store('workspace-b','feature') is None
    draft_store('workspace-a','feature',model,model);assert draft_store('workspace-a','feature') is None


def test_helper_cycles_and_cancellation_are_explicit(tmp_path):
    from threading import Event
    import pytest
    from changelens.core import Cancelled
    fixture(tmp_path);p=tmp_path/'service.js';p.write_text("import {calendar} from './controller.js';export async function read(id){return calendar(id);}")
    snapshot=index_repository(tmp_path);flow=analyze_flows(snapshot)['flows'][0]
    assert any('cycle' in g for g in flow['gaps'])
    cancel=Event();cancel.set()
    with pytest.raises(Cancelled):analyze_flows(snapshot,cancel)


def test_shadowed_model_is_not_a_database_link(tmp_path):
    fixture(tmp_path);(tmp_path/'service.js').write_text("import Calendar from './model.js';export async function read(Calendar){return Calendar.find({InstituteId:1});}")
    flow=analyze_flows(index_repository(tmp_path))['flows'][0]
    assert flow['matches'][0]['service_helpers'][0]['data']==[]


def test_new_model_import_rejoins_without_reparsing_call_site(tmp_path):
    from changelens.feature_flows import _MODULE_CACHE
    _MODULE_CACHE.clear()
    fixture(tmp_path);(tmp_path/'model.js').unlink()
    first=analyze_flows(index_repository(tmp_path))['flows'][0]
    assert first['matches'][0]['service_helpers'][0]['data']==[]
    (tmp_path/'model.js').write_text('export default {};')
    second=analyze_flows(index_repository(tmp_path))['flows'][0]
    assert second['matches'][0]['service_helpers'][0]['data'][0]['operation']=='Calendar.find'
