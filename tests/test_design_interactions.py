import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import pytest
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from changelens.design_canvas import EditableDesign


def sample_model():
    return {'format':'changelens-design','version':1,'snapshot_id':'test','project':'demo','level':'LLD','scope':'test','page':0,
        'nodes':[{'id':sid,'title':sid,'kind':'class','fields':[],'operations':['work()'],'x':i*420,'y':0,'origin':'extracted'} for i,sid in enumerate(['one','two','untouched'])],
        'edges':[{'id':'edge','from':'one','to':'two','label':'calls','origin':'extracted','classification':'resolved static'}]}


def positions(editor):return {r['id']:(r['x'],r['y']) for r in editor.model['nodes']}


def drag_view(editor,app,start,delta,button=Qt.MouseButton.LeftButton,modifiers=Qt.KeyboardModifier.NoModifier):
    viewport=editor.view.viewport();end=start+delta
    QTest.mousePress(viewport,button,modifiers,start)
    app.sendEvent(viewport,QMouseEvent(QEvent.Type.MouseMove,QPointF(end),QPointF(viewport.mapToGlobal(end)),Qt.MouseButton.NoButton,button,modifiers))
    QTest.mouseRelease(viewport,button,modifiers,end);app.processEvents()


@pytest.mark.parametrize('level',['HLD','LLD'])
def test_background_middle_space_and_pan_tool_move_view_only(level):
    app=QApplication.instance() or QApplication([]);editor=EditableDesign();editor.resize(1500,800)
    model=sample_model();model['level']=level;editor.set_model(model);editor.show();app.processEvents();editor.frame_readable();app.processEvents()
    before=positions(editor);view=editor.view
    def center():return view.mapToScene(view.viewport().rect().center())
    start=QPoint(15,view.viewport().height()-15);original=center()
    # Multiple drags beyond the original tight scene rectangle must keep working.
    for _ in range(5):drag_view(editor,app,start,QPoint(110,75))
    assert center().x()<original.x()-500 and center().y()<original.y()-300
    view.centerOn(editor.nodes['one'].sceneBoundingRect().center());app.processEvents()
    point=view.mapFromScene(editor.nodes['one'].sceneBoundingRect().center());original=center()
    drag_view(editor,app,point,QPoint(-80,-50),Qt.MouseButton.MiddleButton)
    assert center()!=original
    view.setFocus();QTest.keyPress(view,Qt.Key.Key_Space);point=view.mapFromScene(editor.nodes['one'].sceneBoundingRect().center());original=center()
    drag_view(editor,app,point,QPoint(65,40));QTest.keyRelease(view,Qt.Key.Key_Space)
    assert center()!=original and not view._space
    editor.pan_button.setChecked(True);point=view.mapFromScene(editor.nodes['one'].sceneBoundingRect().center());original=center()
    drag_view(editor,app,point,QPoint(35,25));assert center()!=original
    assert positions(editor)==before and editor.history.count()==0
    editor.pan_button.setChecked(False);editor.close();app.processEvents()


def test_shift_box_selection_wheel_trackpad_zoom_and_focus_reset():
    from PySide6.QtGui import QWheelEvent,QFocusEvent
    app=QApplication.instance() or QApplication([]);editor=EditableDesign();editor.resize(1700,900);editor.set_model(sample_model());editor.show();app.processEvents();editor.frame_readable();app.processEvents();view=editor.view
    start=view.mapFromScene(QPointF(-20,-20));end=view.mapFromScene(QPointF(800,160))
    drag_view(editor,app,start,end-start,modifiers=Qt.KeyboardModifier.ShiftModifier)
    assert {i.record['id'] for i in editor.scene.selectedItems() if hasattr(i,'record')}=={'one','two'}
    point=QPoint(160,160)
    def wheel(pixel,angle,mod=Qt.KeyboardModifier.NoModifier):
        app.sendEvent(view.viewport(),QWheelEvent(QPointF(point),QPointF(view.viewport().mapToGlobal(point)),pixel,angle,Qt.MouseButton.NoButton,mod,Qt.ScrollPhase.NoScrollPhase,False))
    before=view.mapToScene(point);scale=view.transform().m11()
    wheel(QPoint(),QPoint(0,120),Qt.KeyboardModifier.ControlModifier)
    assert view.transform().m11()>scale and (view.mapToScene(point)-before).manhattanLength()<4
    before=view.mapToScene(point);wheel(QPoint(32,-24),QPoint());assert view.mapToScene(point)!=before
    before=view.mapToScene(point);wheel(QPoint(),QPoint(0,-120),Qt.KeyboardModifier.ShiftModifier)
    assert view.mapToScene(point).x()>before.x()
    view.setFocus();QTest.keyPress(view,Qt.Key.Key_Space);view.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut));assert not view._space and view._pan_pos is None
    editor.close();app.processEvents()


def drag_card(editor,app,sid,delta=QPoint(55,35)):
    editor.pan_button.setChecked(False)
    start=editor.view.mapFromScene(editor.nodes[sid].sceneBoundingRect().center());end=start+delta;viewport=editor.view.viewport()
    QTest.mousePress(viewport,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start)
    move=QMouseEvent(QEvent.Type.MouseMove,QPointF(end),QPointF(viewport.mapToGlobal(end)),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    app.sendEvent(viewport,move)
    QTest.mouseRelease(viewport,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end)
    app.processEvents()


def test_drag_selected_cards_commits_all_positions_as_one_undo_step():
    app=QApplication.instance() or QApplication([]);editor=EditableDesign();editor.resize(1600,850);editor.set_model(sample_model());editor.show();app.processEvents()
    editor.nodes['one'].setSelected(True);editor.nodes['two'].setSelected(True);app.processEvents();editor.frame_readable();app.processEvents()
    before=positions(editor);drag_card(editor,app,'one');after=positions(editor)
    delta=(after['one'][0]-before['one'][0],after['one'][1]-before['one'][1])
    assert delta!=(0,0)
    assert (after['two'][0]-before['two'][0],after['two'][1]-before['two'][1])==pytest.approx(delta)
    assert after['untouched']==before['untouched']
    assert editor.history.count()==1 and editor.history.undoText()=='Move selected cards'
    assert {item.record['id'] for item in editor.scene.selectedItems()}=={'one','two'}
    edge=editor.edges[0][0];assert edge.path().pointAtPercent(0).x()>=after['one'][0]
    editor.history.undo();assert positions(editor)==before
    assert {item.record['id'] for item in editor.scene.selectedItems()}=={'one','two'}
    editor.history.redo();assert positions(editor)==after
    drag_card(editor,app,'two',QPoint(30,20));assert editor.history.count()==2
    again=positions(editor);assert again['one']!=after['one'] and again['two']!=after['two']
    editor.close();app.processEvents()


def test_single_card_drag_and_group_positions_survive_design_roundtrip(tmp_path):
    import json
    from changelens.design_canvas import validate_model
    app=QApplication.instance() or QApplication([]);editor=EditableDesign();editor.resize(1500,800);editor.set_model(sample_model());editor.show();app.processEvents()
    editor.nodes['one'].setSelected(True);app.processEvents();editor.frame_readable();app.processEvents();before=positions(editor)
    drag_card(editor,app,'one');after=positions(editor)
    assert after['one']!=before['one'] and after['two']==before['two']
    editor.nodes['two'].setSelected(True);editor.move_nodes({'one':(100,120),'two':(520,120)})
    stored=tmp_path/'group.cldesign.json';stored.write_text(json.dumps(editor.model));loaded=json.loads(stored.read_text());validate_model(loaded)
    editor.set_model(loaded);assert positions(editor)['two']==(520,120) and positions(editor)['one']==(100,120)
    editor.close();app.processEvents()


def test_optional_3d_has_xyz_orbit_reset_picking_and_shared_evidence(tmp_path,monkeypatch):
    from changelens.workbench import MainWindow
    from test_lens import wait
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'));monkeypatch.setenv('CHANGELENS_TEST_NO_AI','1')
    (tmp_path/'source.py').write_text('def source():return 1\ndef first():return source()\ndef second():return source()\ndef app():return first()+second()\n')
    app=QApplication.instance() or QApplication([]);window=MainWindow();window.resize(1500,850);window.show();window.open_path(tmp_path);wait(app,window)
    window.navigate(6);window.pages.finish_transition()
    lens=window.lens_view;lens.show_root('source.py:source');assert lens.mode.currentIndex()==0
    assert [lens.mode.itemText(i) for i in range(lens.mode.count())]==['Impact map','Layers','3D']
    lens.mode.setCurrentIndex(2);app.processEvents();view=lens.perspective_map
    assert lens.map_stack.currentWidget() is view and set(view.rows)==set(lens.spatial_map.rows)==set(lens.rows)
    assert view.positions['source.py:first'][2]!=view.positions['source.py:second'][2]
    assert view.edges==lens.spatial_map.edges
    old=view.project(view.positions['source.py:first'])[0];QTest.keyClick(view,Qt.Key.Key_Right)
    assert view.project(view.positions['source.py:first'])[0]!=old
    QTest.keyClick(view,Qt.Key.Key_Home);assert view.project(view.positions['source.py:first'])[0]==old
    app.processEvents();assert view.hitboxes and view.visible_labels
    for i,(rect,_) in enumerate(view.label_hits):assert not any(rect.intersects(other) for other,_ in view.label_hits[i+1:])
    rect,sid=view.label_hits[0];QTest.mouseClick(view,Qt.MouseButton.LeftButton,pos=rect.center().toPoint());app.processEvents()
    assert lens.selected_sid==sid and lens.detail.isVisible()
    frozen=deepcopy(view.positions)
    for hits in (view.label_hits,view.hitboxes):
        rect,sid=hits[0];start=rect.center().toPoint();end=start+QPoint(60,35)
        QTest.mousePress(view,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start)
        app.sendEvent(view,QMouseEvent(QEvent.Type.MouseMove,QPointF(end),QPointF(view.mapToGlobal(end)),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier))
        QTest.mouseRelease(view,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end);app.processEvents()
        assert view.positions==frozen and lens.selected_sid==sid
    start=QPoint(8,view.height()-45);end=start+QPoint(35,-20);yaw=view.yaw
    QTest.mousePress(view,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start)
    app.sendEvent(view,QMouseEvent(QEvent.Type.MouseMove,QPointF(end),QPointF(view.mapToGlobal(end)),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier))
    QTest.mouseRelease(view,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end);app.processEvents()
    assert view.yaw!=yaw and view.positions==frozen
    lens.mode.setCurrentIndex(1);assert lens.map_stack.currentWidget() is lens.spatial_map
    lens.mode.setCurrentIndex(0);assert lens.map_stack.currentWidget() is lens.map
    window.close();app.processEvents()


def test_large_design_uses_prepared_scope_index_and_keeps_cache_out_of_json(tmp_path,monkeypatch):
    import json
    from changelens.architecture import review_architecture
    from changelens.core import index_repository
    from changelens.architecture_ui import ArchitectureView
    from changelens import design_diagrams
    report=dict(review_architecture(index_repository(tmp_path)))
    report['symbols']=[{'id':f'pkg{n%500}/file{n}.py:fn','name':f'fn{n}','qualname':f'fn{n}','path':f'pkg{n%500}/file{n}.py',
        'kind':'function','start':1,'end':2,'is_test':False,'owner':None,'fields':[],'bases':[],'constructors':[],
        'signature':f'fn{n}()','header':f'def fn{n}()'} for n in range(10000)]
    report['summary'].update(files=10000,symbols=10000)
    indexed=design_diagrams.prepare_diagrams(report)
    def rescan(*args,**kwargs):raise AssertionError('Prepared UI index must not rescan declaration paths for each group')
    monkeypatch.setattr(design_diagrams,'scope_for',rescan)
    assert len(design_diagrams.scopes(indexed))==500
    for scope in design_diagrams.scopes(indexed):assert len(design_diagrams.candidates(indexed,scope))==20
    app=QApplication.instance() or QApplication([]);view=ArchitectureView();view.set_report(indexed)
    assert view.scope.count()==501 and view.diagram.renderer().isValid()
    serialized=json.loads(json.dumps(indexed));assert 'scope_groups' not in serialized and 'all_candidates' not in serialized
    view.close();app.processEvents()
