"""Controlled native/frozen checks; no external repository execution."""
import json
import os
from pathlib import Path
import tempfile
import time


def run(output):
    os.environ['CHANGELENS_TEST_NO_AI']='1'
    from PySide6.QtCore import QTimer,Qt,QPoint,QPointF,QEvent
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from .workbench import MainWindow
    from .architecture import export_bundle
    from .core import app_dir
    app=QApplication.instance() or QApplication([])
    workspace=tempfile.TemporaryDirectory(prefix='architecture-smoke-',dir=app_dir())
    root=Path(workspace.name)
    (root/'a.py').write_text('from b import work\nclass Service:\n    value: int = 0\n    def run(self, n: int) -> int:\n        return work(n)\ndef entry(n): return work(n)\n',encoding='utf-8')
    (root/'b.py').write_text('from a import entry\ndef work(n): return entry(n) if n else 0\n',encoding='utf-8')
    (root/'test_a.py').write_text('from a import entry\ndef test_entry(): assert entry(0) == 0\n',encoding='utf-8')
    (root/'server.js').write_text("import express from 'express';const app=express();app.get('/api/calendar/:id',(req,res)=>res.status(200).json({data:[]}));",encoding='utf-8')
    (root/'screen.jsx').write_text("import axios from 'axios';import {useState} from 'react';export function Calendar(){const [items,setItems]=useState([]);async function load(){const response=await axios.get(`/api/calendar/${id}`);setItems(response.data.data);}return <div><label for=\"calendar\">Date & Month</label>{items.map(x=><p>{x.month}</p>)}</div>;}",encoding='utf-8')
    output.parent.mkdir(parents=True,exist_ok=True);checks=[];stage=0;started=time.monotonic()
    window=MainWindow();window.show();timer=QTimer()
    def finish(error=None):
        timer.stop();output.write_text(json.dumps({'passed':not error,'checks':checks,'failures':[str(error)] if error else []},indent=2),encoding='utf-8')
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
                window.navigate(6);view=window.lens_view;view.focus.setCurrentIndex(view.focus.findData('b.py:work'));view.focus_changed();view.mode.setCurrentIndex(1)
                assert view.map_stack.currentWidget() is view.spatial_map
                assert set(view.rows)==set(view.spatial_map.positions)
                sid=next(iter(view.rows));view.spatial_map.select_node(sid)
                assert view.selected_sid==sid and view.detail.isVisible();checks.append('dependency layers use the same static relationships and evidence drawer')
                previous=(view.spatial_map.pan.x(),view.spatial_map.pan.y());QTest.keyClick(view.spatial_map,Qt.Key.Key_Right);assert (view.spatial_map.pan.x(),view.spatial_map.pan.y())!=previous,'Layer keyboard pan did not move'
                QTest.keyClick(view.spatial_map,Qt.Key.Key_Home);checks.append('native dependency-layer pan and reset')
                view.mode.setCurrentIndex(2);app.processEvents();assert view.map_stack.currentWidget() is view.perspective_map
                assert view.perspective_map.edges==view.spatial_map.edges
                previous=view.perspective_map.yaw;QTest.keyClick(view.perspective_map,Qt.Key.Key_Right);assert view.perspective_map.yaw!=previous
                QTest.keyClick(view.perspective_map,Qt.Key.Key_Home);assert view.perspective_map.yaw==previous
                app.processEvents();spatial=view.perspective_map;spatial.grab();fixed=json.loads(json.dumps(spatial.positions));rect,_=spatial.label_hits[0];start=rect.center().toPoint();end=start+QPoint(45,25)
                QTest.mousePress(spatial,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start)
                app.sendEvent(spatial,QMouseEvent(QEvent.Type.MouseMove,QPointF(end),QPointF(spatial.mapToGlobal(end)),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier))
                QTest.mouseRelease(spatial,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end);app.processEvents();assert spatial.positions==fixed,'3D node coordinates changed during a drag'
                checks.append('3D node / label dragging cannot change world coordinates')
                window.grab().save(str(output.with_name(output.stem+'_3d.png')));checks.append('optional genuine 3D projection, shared evidence, orbit and reset')
                view.mode.setCurrentIndex(0);assert view.map_stack.currentWidget() is view.map
                window.navigate(8)
            elif stage==2:
                report=window.architecture_view.report;assert report
                assert not any(w.startswith('Cannot parse') for w in report['warnings'])
                assert report['review']['items'] and any(i['evidence'] for i in report['review']['items'] if i['kind']=='dependency_cycle')
                assert 'heuristic findings' not in window.architecture_view.overview.toPlainText()
                checks.append('JSX keyword / ampersand compatibility and source-backed grouped review queue')
                flows=window.architecture_view.flows;assert report['feature_flows']['summary']['path_matches']==1
                assert window.architecture_view.tabs.currentWidget() is flows
                flows.search.setText('Calendar');flows.features.setCurrentRow(0);app.processEvents()
                assert any(n['kind']=='UI rendering' for n in flows.canvas.model['nodes'])
                canvas=flows.canvas;ids=list(canvas.nodes)[:2];original={sid:(canvas.nodes[sid].pos().x(),canvas.nodes[sid].pos().y()) for sid in ids}
                for sid in ids:canvas.nodes[sid].setSelected(True)
                app.processEvents();canvas.view.centerOn(canvas.nodes[ids[0]].sceneBoundingRect().center());app.processEvents()
                start=canvas.view.mapFromScene(canvas.nodes[ids[0]].sceneBoundingRect().center());end=start+QPoint(40,25);viewport=canvas.view.viewport()
                QTest.mousePress(viewport,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start)
                app.sendEvent(viewport,QMouseEvent(QEvent.Type.MouseMove,QPointF(end),QPointF(viewport.mapToGlobal(end)),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier))
                QTest.mouseRelease(viewport,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end);app.processEvents()
                delta=[(canvas.nodes[sid].pos().x()-original[sid][0],canvas.nodes[sid].pos().y()-original[sid][1]) for sid in ids]
                assert delta[0]!=(0,0) and abs(delta[0][0]-delta[1][0])<.001 and abs(delta[0][1]-delta[1][1])<.001,'Selected cards did not move together'
                canvas.history.undo();assert all((canvas.nodes[sid].pos().x(),canvas.nodes[sid].pos().y())==original[sid] for sid in ids)
                canvas.scene.clearSelection();checks.append('native multi-card drag commits the group and one Undo restores all positions')
                count=len(flows.canvas.model['nodes']);flows.canvas.add_node('note');flows.canvas.history.undo();assert len(flows.canvas.model['nodes'])==count
                flows.canvas.fit();window.grab().save(str(output.with_name(output.stem+'_feature.png')))
                checks.append('native feature search, mounted endpoint candidate, response / state / rendering, editable draft undo')
                assert any(f['kind']=='dependency_cycle' for f in report['findings'])
                assert any(s['signature']=='run(self, n: int) -> int' for s in report['symbols'])
                checks.append('offline LLD signatures, class fields and evidence-backed dependency cycle')
                window.architecture_view.tabs.setCurrentIndex(3);assert window.architecture_view.diagram.renderer().isValid()
                window.grab().save(str(output.with_name(output.stem+'_diagram.png')))
                exported=export_bundle(report,window.architecture_snapshot,root)
                assert all((exported/name).exists() for name in ['report.json','report.md','architecture.svg','lld.svg'])
                checks.append('standalone JSON, Markdown and SVG export')
                canvas=window.architecture_view.canvas;window.architecture_view.diagram_choice.setCurrentIndex(1)
                assert canvas.model['level']=='LLD'
                count=len(canvas.model['nodes']);canvas.add_node('note');assert len(canvas.model['nodes'])==count+1
                canvas.history.undo();assert len(canvas.model['nodes'])==count
                canvas.history.redo();assert len(canvas.model['nodes'])==count+1
                canvas.write_svg(output.with_name(output.stem+'_draft.svg'))
                from .design_canvas import validate_model
                validate_model(json.loads(json.dumps(canvas.model)))
                checks.append('editable LLD note, undo/redo, design roundtrip and draft SVG export')
                assert (exported/'lld-index.md').exists() and list((exported/'lld').glob('detail-*.svg'))
                checks.append('explicit HLD overview and complete paginated LLD detail book')
                (root/'a.py').write_text('def changed(): return 2\n',encoding='utf-8')
                try:export_bundle(report,window.architecture_snapshot,root)
                except ValueError:checks.append('stale architecture export rejected')
                else:raise AssertionError('stale export accepted')
                finish();return
            stage+=1
        except Exception as exc:
            import traceback
            finish(traceback.format_exc())
    timer.timeout.connect(tick);timer.start(100)
    return app.exec()
