import json
from threading import Event
import xml.etree.ElementTree as ET
import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from changelens.core import index_repository, Cancelled
from changelens.architecture import review_architecture, diagram_svg, export_bundle, components
from test_core import write


def project(root):
    write(root,'a.py','from b import second\nclass Service:\n    kind: str = "demo"\n    def __init__(self, value: int):\n        self.value: int = value\n    def run(self, count: int = 1) -> int:\n        return second(count)\ndef first(n): return second(n)\n')
    write(root,'b.py','from a import first\ndef second(n): return first(n) if n else 0\n')
    write(root,'test_a.py','from a import first\ndef test_first(): assert first(0) == 0\n')
    return index_repository(root)


def test_lld_fields_signatures_cycles_and_evidence_without_execution(tmp_path):
    snap=project(tmp_path);report=review_architecture(snap)
    rows={s['id']:s for s in report['symbols']}
    assert rows['a.py:Service.run']['owner']=='a.py:Service'
    assert rows['a.py:Service.run']['signature']=='run(self, count: int=1) -> int'
    assert {'name':'value','annotation':'int'} in rows['a.py:Service']['fields']
    cycle=next(f for f in report['findings'] if f['kind']=='dependency_cycle')
    assert cycle['locations']==['a.py','b.py'] and cycle['evidence']
    assert all(e['evidence'] for e in report['dependencies'])
    assert report['snapshot_id']==snap.id


def test_export_snapshot_freshness_escaping_and_standalone_diagrams(tmp_path):
    root=tmp_path/'source space ü';root.mkdir();snap=project(root);report=review_architecture(snap)
    out=export_bundle(report,snap,tmp_path)
    assert {p.name for p in out.iterdir()}=={'report.md','report.json','architecture.svg','lld.svg','lld-index.md','lld'}
    assert json.loads((out/'report.json').read_text(encoding='utf-8'))['hashes']==snap.hashes
    for name in ['architecture.svg','lld.svg']:ET.parse(out/name)
    report['project']='<script>&"';assert '&lt;script&gt;&amp;' in diagram_svg(report)
    write(root,'b.py','def changed(): return 1')
    with pytest.raises(ValueError,match='Project changed'):export_bundle(report,snap,tmp_path)


def test_cancel_and_large_iterative_graph(tmp_path):
    snap=project(tmp_path);cancel=Event();cancel.set()
    with pytest.raises(Cancelled):review_architecture(snap,cancel)
    graph={str(i):{str(i+1)} for i in range(2000)};graph['2000']={'1999'}
    assert components(graph)==[['1999','2000']]


def test_inferred_cycle_is_not_reported_as_resolved(tmp_path):
    snap=project(tmp_path)
    # Suppress the separate import inventory to isolate inferred call relationships.
    from unittest.mock import patch
    for edge in snap.edges:edge['kind']='inferred_method'
    with patch('changelens.architecture.python_import_dependencies',return_value=([],[])):
        report=review_architecture(snap)
    assert not any(f['kind']=='dependency_cycle' for f in report['findings'])
    assert all(d['classification']=='inferred' for d in report['dependencies'])


def test_native_3d_projection_selection_orbit_and_reset():
    from changelens.lens3d import SpatialLens
    app=QApplication.instance() or QApplication([]);view=SpatialLens();view.resize(1000,650);view.show()
    rows=[{'symbol':s,'distance':d} for s,d in [('a',0),('b',1),('c',1),('d',2)]]
    edges=[{'caller':b,'callee':a,'kind':'static_reference'} for a,b in [('a','b'),('a','c'),('b','d'),('c','d')]]
    view.set_records(rows,edges,{},'a');app.processEvents()
    assert len(view.positions)==4 and len(view.hitboxes)==4
    assert view.positions['b'][2]==view.positions['c'][2]  # one fixed depth per dependency layer
    assert view.positions['b'][1]!=view.positions['c'][1]  # readable nonoverlapping cards
    view.select_node('d');assert view.active=={'a','b','c','d'}
    before=view.project(view.positions['b'])[0];QTest.keyClick(view,Qt.Key.Key_Right)
    assert view.project(view.positions['b'])[0]!=before
    QTest.keyClick(view,Qt.Key.Key_Home);assert view.project(view.positions['b'])[0]==before
    view.set_records(rows,edges,{},'__all_changes__');assert view.active=={'a','b','c','d'}
    view.close()


def test_ui_architecture_and_shared_3d_evidence(tmp_path,monkeypatch):
    from changelens.workbench import MainWindow
    from test_lens import wait
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'));monkeypatch.setenv('CHANGELENS_TEST_NO_AI','1')
    root=tmp_path/'project';root.mkdir();project(root)
    app=QApplication.instance() or QApplication([]);window=MainWindow();window.show();window.open_path(root);wait(app,window)
    window.navigate(8);app.processEvents();wait(app,window)
    assert window.architecture_view.report and window.architecture_view.declarations.topLevelItemCount()
    assert not window._pending_error
    saves=[];monkeypatch.setattr(window.architecture_view.canvas,'save_design',lambda:saves.append(True))
    window.save_current();assert saves==[True]
    window.navigate(6);view=window.lens_view;view.mode.setCurrentIndex(1)
    assert view.map_stack.currentWidget() is view.spatial_map
    sid=next(iter(view.rows));view.spatial_map.select_node(sid)
    assert view.selected_sid==sid and view.detail.isVisible()
    window.architecture_view.open_item(window.architecture_view.declarations.topLevelItem(0))
    assert window.pages.currentIndex()==0
    window.close();app.processEvents()


def test_import_only_relative_modules_and_ambiguous_roots(tmp_path):
    write(tmp_path,'pkg/__init__.py','')
    write(tmp_path,'pkg/a.py','from . import b\nraise RuntimeError("must never execute")\n')
    write(tmp_path,'pkg/b.py','from .a import missing\n')
    write(tmp_path,'duplicate.py','')
    write(tmp_path,'src/duplicate.py','')
    write(tmp_path,'consumer.py','import duplicate\n')
    report=review_architecture(index_repository(tmp_path))
    links={(e['from'],e['to']) for e in report['dependencies']}
    assert ('pkg/a.py','pkg/b.py') in links and ('pkg/b.py','pkg/a.py') in links
    assert not any(a=='consumer.py' for a,b in links)
    assert any('Ambiguous local architecture import' in w for w in report['warnings'])


def test_paginated_design_book_covers_all_without_generated_noise(tmp_path):
    from changelens.design_diagrams import book,candidates,render,scopes
    for i in range(27):write(tmp_path,f'lib/features/maps/unit{i}.dart',f'class Item{i} {{ final int count = 1; Item{i}(); int run(int n) {{ return n; }} }}')
    write(tmp_path,'android/GeneratedPluginRegistrant.java','class GeneratedPluginRegistrant {}')
    write(tmp_path,'test/a.dart','class TestOnly {}')
    report=review_architecture(index_repository(tmp_path));pages,index=book(report)
    assert len(candidates(report,'lib/features/maps'))==27
    combined=''.join(pages.values())
    for i in range(27):assert f'Item{i}<' in combined
    assert 'GeneratedPluginRegistrant' not in combined and 'TestOnly' not in combined
    assert 'page 3' in index
    row=next(r for r in report['symbols'] if r['name']=='Item1')
    assert row['fields']==[{'name':'count','annotation':'int'}] and row['constructors']==['Item1()']
    method=next(r for r in report['symbols'] if r['qualname']=='Item1.run')
    assert method['signature']=='int run(int n)'
    svg=render(report,True,'lib/features/maps');assert 'count: int' in svg and 'int run(int n)' in svg
    for svg in pages.values():ET.fromstring(svg)


def test_dart_enum_and_type_links_are_explicitly_unverified(tmp_path):
    from changelens.design_diagrams import class_edges
    write(tmp_path,'lib/domain.dart','enum Tool { select, move }\nclass Store {}\nclass Workspace { final Store store; Workspace(this.store); }')
    report=review_architecture(index_repository(tmp_path));rows={r['name']:r for r in report['symbols']}
    assert rows['Tool']['declaration_kind']=='enum' and rows['Tool']['enum_values']==['select','move']
    assert (rows['Workspace']['id'],rows['Store']['id'],'declared type (unverified)',1) in class_edges(report)


def test_spatial_labels_do_not_overlap():
    from changelens.lens3d import SpatialLens
    app=QApplication.instance() or QApplication([]);view=SpatialLens();view.resize(1200,720);view.show()
    rows=[{'symbol':f'file.py:node{i}','distance':i//6} for i in range(30)]
    view.set_records(rows,[],{},rows[0]['symbol']);app.processEvents()
    labels=[rect for rect,sid in view.label_hits]
    assert labels and len(labels)==len(rows)  # every layer card carries its own label
    assert not any(a.intersects(b) for i,a in enumerate(labels) for b in labels[i+1:])
    for rect,sid in view.label_hits:assert view.node_at(rect.center())==sid
    view.close()


def test_editable_hld_lld_details_undo_edges_and_svg(tmp_path):
    from changelens.design_canvas import EditableDesign,extracted_model,validate_model
    app=QApplication.instance() or QApplication([]);report=review_architecture(project(tmp_path))
    model=extracted_model(report,'LLD','.')
    validate_model(model);editor=EditableDesign();editor.set_model(model);editor.resize(1200,800);editor.show();app.processEvents()
    sid='a.py:Service';editor.nodes[sid].setSelected(True)
    editor.title.setText('ReviewedService');editor.fields.setPlainText('value: int\ncache: dict');editor.apply_properties()
    row=next(r for r in editor.model['nodes'] if r['id']==sid)
    assert row['title']=='ReviewedService' and row['origin']=='edited' and row['original']['title']=='Service'
    editor.history.undo();assert next(r for r in editor.model['nodes'] if r['id']==sid)['title']=='Service'
    editor.history.redo();assert next(r for r in editor.model['nodes'] if r['id']==sid)['title']=='ReviewedService'
    editor.add_node('note');assert editor.model['nodes'][-1]['kind']=='note'
    old_edges=len(editor.model['edges']);editor.source.setCurrentIndex(0);editor.target.setCurrentIndex(editor.target.count()-1);editor.add_edge()
    assert len(editor.model['edges'])==old_edges+1 and editor.model['edges'][-1]['classification']=='user proposal'
    editor.write_svg(tmp_path/'draft.svg');ET.parse(tmp_path/'draft.svg')
    assert 'DESIGN DRAFT' in (tmp_path/'draft.svg').read_text(encoding='utf-8')
    from PySide6.QtWidgets import QFileDialog
    stored=json.loads(json.dumps(editor.model));validate_model(stored)
    assert (tmp_path/'a.py').read_text().startswith('from b import second')
    stored['nodes'][0]['x']=float('nan')
    with pytest.raises(ValueError):validate_model(stored)
    editor.close()


def test_canvas_scope_edits_survive_navigation(tmp_path,monkeypatch):
    from changelens.architecture_ui import ArchitectureView
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'))
    app=QApplication.instance() or QApplication([]);view=ArchitectureView();view.set_report(review_architecture(project(tmp_path)));view.show();app.processEvents()
    view.diagram_choice.setCurrentIndex(1);app.processEvents()
    assert view.canvas.model['level']=='LLD'
    view.canvas.add_node('note');count=len(view.canvas.model['nodes'])
    view.diagram_choice.setCurrentIndex(0);app.processEvents();assert view.canvas.model['level']=='HLD'
    view.diagram_choice.setCurrentIndex(1);app.processEvents();assert len(view.canvas.model['nodes'])==count
    report=view.report;view.close()
    restored=ArchitectureView();restored.set_report(report);restored.diagram_choice.setCurrentIndex(1);app.processEvents()
    assert len(restored.canvas.model['nodes'])==count
    restored.close()


def test_background_refresh_does_not_replace_reviewed_patch(tmp_path,monkeypatch):
    from changelens.workbench import MainWindow
    from test_lens import wait
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'));monkeypatch.setenv('CHANGELENS_TEST_NO_AI','1')
    app=QApplication.instance() or QApplication([]);root=tmp_path/'p';root.mkdir();project(root)
    window=MainWindow();window.open_path(root);wait(app,window)
    marker={'operation':'ai_rewrite'};window.patch=marker;window.patch_stale=False
    window.automatic_check();assert window.worker is None and window.patch is marker
    window.patch=None;window.close();app.processEvents()
