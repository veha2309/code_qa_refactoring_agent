import json
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from xml.etree import ElementTree
from PySide6.QtWidgets import QApplication
from changelens.core import index_repository
from changelens.architecture import review_architecture,export_bundle
from changelens.feature_flows import analyze_flows,design_model,model_svg
from changelens.design_canvas import validate_model


def project(root):
    files={
        'app.js':"import exp from 'express';import secured from './secured.js';const app=exp();app.use('/secured',secured,addError);",
        'secured.js':"import express from 'express';import academic from './routes.js';const router=express.Router();router.use('/academic',auth,featureCheck(['Basic']),academic);export default router;",
        'routes.js':"import {Router} from 'express';import {load as getCalendar} from './controller.js';const router=Router();router.get('/calendar/:id',getCalendar);export default router;",
        'controller.js':"import Calendar from './model.js';export const load=async(req,res)=>{const {id}=req.params;const result=await Calendar.find({InstituteId:id});if(!result)return res.status(404).json({message:'missing'});const payload={status:true,data:result};return res.status(200).json(payload);}",
        'model.js':'export default {};',
        'cms/src/client.js':"import axios from 'axios';const api=axios.create({baseURL:process.env.API_URL});export default api;",
        'cms/src/Calendar.jsx':"import api from './client';import {useState,useEffect} from 'react';export function CalendarList(){const [items,setItems]=useState([]);useEffect(()=>{async function fetchItems(){const response=await api.get(`/secured/academic/calendar/${id}?lang=all`);setItems(response.data.data);}fetchItems();},[]);return <div>{items.map(x=><h4>{x.month}</h4>)}</div>; }"
    }
    for path,src in files.items():
        target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(src,encoding='utf-8')
    return index_repository(root)


def test_nested_mounts_aliases_error_middleware_handler_data_and_ui(tmp_path):
    snapshot=project(tmp_path);data=analyze_flows(snapshot)
    assert data['summary']['requests']==1 and data['summary']['path_matches']==1
    flow=data['flows'][0];route=flow['matches'][0];handler=route['handler_detail']
    assert route['endpoint']=='/secured/academic/calendar/:id'
    assert route['mounts'][0]['target']=='secured' and route['mounts'][0]['middleware']==['addError']
    assert route['mounts'][1]['middleware']==['auth','featureCheck(…)']
    assert handler['name']=='load' and handler['inputs']==['req.params.id']
    assert handler['data'][0]['operation']=='Calendar.find' and handler['data'][0]['filter_fields']==['InstituteId']
    assert {r['status'] for r in handler['responses']}=={'200','404'}
    assert handler['conditions'][0]['description']=='Condition: (!result)'
    assert handler['responses'][1]['fields']==['status','data']
    assert flow['updates'][0]['state']=='items' and flow['updates'][0]['renders'][0]['state']=='items'
    assert flow['app']=='cms' and 'not verified' in flow['origin']


def test_comments_non_http_getters_and_shadowed_clients_do_not_make_flows(tmp_path):
    project(tmp_path)
    path=tmp_path/'cms/src/Calendar.jsx'
    path.write_text("import api from './client';// api.get('/fake')\nfunction x(api){api.get('/secured/academic/calendar/1');}function y(){const api={get:()=>{}};api.get('/fake');}const store={get(){}};store.get('/fake');")
    assert analyze_flows(index_repository(tmp_path))['flows']==[]


def test_dynamic_prefix_and_wrong_methods_stay_unresolved(tmp_path):
    project(tmp_path);path=tmp_path/'cms/src/Calendar.jsx'
    path.write_text("import api from './client';async function x(){await api.get(`${BASE}/secured/academic/calendar/${id}`);await api.post('/secured/academic/calendar/1');}")
    flows=analyze_flows(index_repository(tmp_path))['flows']
    assert len(flows)==2 and all(f['status']=='unresolved' for f in flows)
    assert flows[0]['endpoint'] is None and any('dynamic prefix' in note for note in flows[0]['notes'])


def test_ambiguous_endpoints_do_not_select_one_server(tmp_path):
    project(tmp_path)
    path=tmp_path/'other.js';path.write_text("import express from 'express';const other=express();other.get('/secured/academic/calendar/:anything',(req,res)=>res.json({data:[]}));")
    flow=analyze_flows(index_repository(tmp_path))['flows'][0]
    assert flow['status']=='ambiguous' and len(flow['matches'])==2


def test_unmounted_router_is_not_reported_as_a_server_connection(tmp_path):
    project(tmp_path);(tmp_path/'app.js').write_text("import express from 'express';const app=express();")
    data=analyze_flows(index_repository(tmp_path))
    assert data['routes'] and not data['routes'][0]['mount_complete']
    assert data['flows'][0]['status']=='unresolved'


def test_manifests_distinguish_web_apps_and_server_outbound_calls(tmp_path):
    project(tmp_path);(tmp_path/'package.json').write_text('{"dependencies":{"express":"4"}}')
    (tmp_path/'cms/package.json').write_text('{"dependencies":{"react":"18"}}')
    (tmp_path/'controller-client.js').write_text("import axios from 'axios';async function notify(){await axios.post('https://example.invalid/other');}")
    flows=analyze_flows(index_repository(tmp_path))['flows']
    web=next(f for f in flows if f['app']=='cms');server=next(f for f in flows if f['path']=='controller-client.js')
    assert web['consumer_kind']=='Web application (manifest)'
    assert server['app']=='Server outbound requests' and server['consumer_kind']=='Server HTTP consumer (manifest)'


def test_response_setter_must_follow_request_in_same_lexical_block(tmp_path):
    project(tmp_path);path=tmp_path/'cms/src/Calendar.jsx'
    path.write_text("import api from './client';import {useState} from 'react';function Calendar(){const [items,setItems]=useState([]);async function load(){setItems(response.data);{const response=await api.get('/secured/academic/calendar/1');}setItems(response.data);}return <div/>;}")
    flow=analyze_flows(index_repository(tmp_path))['flows'][0]
    assert flow['updates']==[]


def test_flow_models_have_explicit_unknowns_source_links_and_standalone_svg(tmp_path):
    snapshot=project(tmp_path);report=review_architecture(snapshot);flow=report['feature_flows']['flows'][0]
    model=design_model(report,flow);validate_model(model)
    assert any(n['kind']=='Data operation' for n in model['nodes'])
    assert any(n['kind']=='UI rendering' for n in model['nodes'])
    assert all(n.get('path') for n in model['nodes'])
    assert any(e['classification']=='path match' for e in model['edges'])
    ElementTree.fromstring(model_svg(model))
    for node in model['nodes']:
        others=[n for n in model['nodes'] if n['x']==node['x'] and n['y']>node['y']]
        if others:
            from changelens.feature_flows import card_height
            assert min(n['y'] for n in others)>=node['y']+card_height(node)
    flow['matches']=[];flow['updates']=[];flow['notes']=['No local endpoint match.'];model=design_model(report,flow)
    assert sum(n['kind']=='Coverage gap' for n in model['nodes'])==2


def test_flow_ui_search_drilldown_edit_undo_and_export(tmp_path,monkeypatch):
    from changelens.architecture_ui import ArchitectureView
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'))
    snapshot=project(tmp_path);report=review_architecture(snapshot)
    app=QApplication.instance() or QApplication([]);view=ArchitectureView();view.resize(1350,850);view.set_report(report);view.show();app.processEvents()
    assert view.tabs.currentWidget() is view.flows
    view.flows.search.setText('calendar');assert view.flows.features.count()==1
    view.flows.features.setCurrentRow(0);app.processEvents();canvas=view.flows.canvas
    assert canvas.model['level']=='LLD' and any(n['kind']=='Data operation' for n in canvas.model['nodes'])
    count=len(canvas.model['nodes']);canvas.add_node('note');assert len(canvas.model['nodes'])==count+1
    canvas.history.undo();assert len(canvas.model['nodes'])==count
    canvas.add_node('note');view.flows.show_systems();view.flows.features.setCurrentRow(0);assert len(canvas.model['nodes'])==count+1
    view.flows.search.setText('no such feature');assert view.flows.features.count()==0 and 'No matching' in view.flows.coverage.text()
    view.close();app.processEvents()
    output=export_bundle(report,snapshot,tmp_path)
    assert (output/'systems.svg').is_file() and (output/'flows.md').is_file()
    assert len(list((output/'flows').glob('*.svg')))==1
    text=(output/'flows.md').read_text(encoding='utf-8');assert 'Calendar.find' in text and 'Client update' in text
    assert 'Representative implementation flow' in (output/'report.md').read_text(encoding='utf-8')


def test_inferences_are_opt_in_and_layers_keep_readable_cards(tmp_path,monkeypatch):
    from changelens.workbench import MainWindow
    from test_lens import wait
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'));monkeypatch.setenv('CHANGELENS_TEST_NO_AI','1')
    (tmp_path/'x.py').write_text('def source():return 1\ndef caller():return source()\ndef broad():return 2\n')
    app=QApplication.instance() or QApplication([]);window=MainWindow();window.open_path(tmp_path);wait(app,window)
    snapshot=window.snapshot;snapshot.edges.append({'caller':'x.py:broad','callee':'x.py:source','line':3,'expression':'scope association','kind':'enclosing_scope'})
    lens=window.lens_view;lens.show_root('x.py:source')
    assert 'x.py:caller' in lens.rows and 'x.py:broad' not in lens.rows
    lens.inferred.setChecked(True);lens.show_root('x.py:source');assert 'x.py:broad' in lens.rows
    assert lens.mode.itemText(1)=='Layers'
    window.close();app.processEvents()
