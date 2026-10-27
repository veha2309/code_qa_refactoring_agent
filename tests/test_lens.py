import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import time
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from changelens.brief import BriefView, brief_markdown
import json
from changelens.lens import map_records
from changelens.ranking import resources
from changelens.workbench import MainWindow


def wait(app,window):
    end=time.monotonic()+12
    while window.worker is not None and time.monotonic()<end:app.processEvents(); time.sleep(.01)
    assert window.worker is None


def test_map_filters_roots_preserves_visible_evidence_and_caps():
    edge={"caller":"b","callee":"a","line":4,"expression":"a()","kind":"static_reference"}
    report={"impact":[{"symbol":"a","path":["a"],"distance":0,"evidence":[]},
                      {"symbol":"b","path":["a","b"],"distance":1,"evidence":[edge]},
                      {"symbol":"other","path":["other"],"distance":0,"evidence":[]}]}
    rows,edges,hidden=map_records(report,"a",1)
    assert [r["symbol"] for r in rows]==["a"] and not edges and hidden==1
    rows,edges,hidden=map_records(report,"a",2)
    assert [r["symbol"] for r in rows]==["a","b"] and edges==[edge] and hidden==0


def test_lens_node_navigation_and_brief_setup(tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path))
    app=QApplication.instance() or QApplication([]); window=MainWindow(); window.show(); window.open_path(resources()/"demo"); wait(app,window)
    assert window.pages.currentIndex()==6 and window.nav.currentItem().text()=="Lens"
    assert window.lens_view.focus.count()>0 and not window.lens_view.trace.isVisible()
    assert not window.project_panel.isVisible() and not window.lens_view.detail.isVisible()
    assert len(window.lens_view.map.nodes)==8  # exploration works without a setup step
    window.lens_view.trace_current(); wait(app,window)
    graph=window.lens_view.map
    assert len(graph.nodes)==8  # selected function, two callers, five statically linked tests
    sid="test_invoice.py:test_invoice_route"
    node=graph.nodes[sid]
    point=graph.mapFromScene(node.sceneBoundingRect().center())
    QTest.mouseClick(graph.viewport(),Qt.MouseButton.LeftButton,pos=point)
    assert window.lens_view.selected_sid==sid
    assert "invoice_route" in window.lens_view.reason.toPlainText()
    assert "Line" in window.lens_view.reason.toPlainText()
    assert graph.nodes["test_invoice.py:test_invoice_zero"].opacity()<1
    assert window.lens_view.detail.isVisible()
    window.lens_view.open_code.click(); app.processEvents()
    assert window.pages.currentIndex()==0 and window.current_document().path.name=="test_invoice.py"
    window.navigate(6); window.lens_view.map.select_node(sid)
    Path("evaluation").mkdir(exist_ok=True); window.grab().save("evaluation/lens_map_preview.png")
    window.assistant_ready=True; window.open_brief()
    assert not window.ai_settings.isVisible()
    window.ai_answer.setPlainText("## What connects\n\n**Resolved:** `invoice_route` calls `create_invoice`.\n\n- Inspect the tax boundary.\n- Run the linked route test.\n\n### Still uncertain\n\nDynamic routing was not executed.")
    assert "**" not in window.ai_answer.toPlainText()
    window.grab().save("evaluation/lens_brief_preview.png")
    window.close(); app.processEvents()


def test_brief_renders_markdown_without_html_or_resource_navigation():
    app=QApplication.instance() or QApplication([])
    view=BriefView(); view.setPlainText("## Heading\n\n**Strong** and `code`.\n\n<b>untrusted HTML</b>\n\n![remote](https://example.invalid/image.png)")
    assert "**Strong**" not in view.toPlainText() and "Heading" in view.toPlainText()
    assert not view.openLinks() and not view.openExternalLinks()
    assert view.loadResource(2,"https://example.invalid/image.png") is None
    view.close(); app.processEvents()


def test_focused_map_keeps_shared_callers_for_every_changed_seed(tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"settings"))
    root=tmp_path/"project"; root.mkdir()
    (root/"a.py").write_text("def alpha(): return 1\ndef beta(): return 2\ndef route(): return alpha() + beta()\n")
    (root/"test_a.py").write_text("from a import route\ndef test_route(): assert route() == 3\n")
    app=QApplication.instance() or QApplication([]); window=MainWindow(); window.show(); window.open_path(root); wait(app,window)
    window.analyze(["a.py:alpha","a.py:beta"]); wait(app,window)
    index=window.lens_view.focus.findData("a.py:beta"); window.lens_view.focus.setCurrentIndex(index); window.lens_view.focus_changed()
    assert window.lens_view.rows["test_a.py:test_route"]["path"]==["a.py:beta","a.py:route","test_a.py:test_route"]
    assert window.lens_view.linked_tests=={"test_a.py:test_route"}
    assert not window.lens_view.detail.isVisible()
    window.close(); app.processEvents()


def test_lens_runs_only_tests_linked_to_the_focused_change(tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"settings"))
    root=tmp_path/"project"; root.mkdir()
    (root/"a.py").write_text("def alpha(): return 1\ndef beta(): return 2\n")
    (root/"test_a.py").write_text("from a import alpha, beta\ndef test_alpha(): assert alpha() == 1\ndef test_beta(): assert beta() == 2\n")
    app=QApplication.instance() or QApplication([]); window=MainWindow(); window.show(); window.open_path(root); wait(app,window)
    window.analyze(["a.py:alpha","a.py:beta"]); wait(app,window)
    window.lens_view.focus.setCurrentIndex(window.lens_view.focus.findData("a.py:beta")); window.lens_view.focus_changed()
    selected=[]; monkeypatch.setattr(window,"validate_demo",lambda mutation=False:selected.extend(window.checked_tests()))
    window.check_and_run()
    assert selected==["test_a.py:test_beta"]
    window.close(); app.processEvents()


def test_brief_length_is_bounded_by_section_instead_of_showing_a_wall():
    answer=json.dumps({"summary":"summary "*200,"uncertainty":"uncertain "*200,"verification":["check "*100]*10})
    rendered=brief_markdown(answer)
    assert rendered.count("\n- ")==3
    assert len(rendered.split())<200 and "## Still uncertain" in rendered and "## What to verify" in rendered
