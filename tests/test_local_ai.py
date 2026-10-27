import ast
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from threading import Event

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from changelens.core import Cancelled, index_repository
from changelens.local_ai import LocalAI, COMPLETION_MODEL, ASSISTANT_MODEL, rewrite_patch
from changelens.widgets import CodeEditor
from changelens.workbench import MainWindow
import time


def fake_client(monkeypatch, response):
    client=LocalAI(); calls=[]
    def request(path,payload=None,cancel=None,timeout=45):
        calls.append((path,payload))
        if path=="/api/show":return {}
        return response
    monkeypatch.setattr(client,"request",request)
    return client,calls


def test_presentation_completion_uses_small_model_fim_and_bounded_context(monkeypatch):
    client,calls=fake_client(monkeypatch,{"response":"value + 1"})
    result=client.complete("# comment\ndef total(value):\n    return ",39,"helper = 2")
    payload=calls[-1][1]
    assert payload["model"]==COMPLETION_MODEL
    assert "<|fim_prefix|>" in payload["prompt"] and "<|fim_suffix|>" in payload["prompt"]
    assert payload["options"]["num_ctx"]==2048 and payload["options"]["num_predict"]==96
    assert payload["raw"] and not payload["stream"] and result["text"]=="value + 1"
    client.complete("x"*20000,15000,"y"*10000)
    assert len(calls[-1][1]["prompt"])<5000


def test_model_switch_unloads_previous_model_and_never_selects_large_model(monkeypatch):
    client,calls=fake_client(monkeypatch,{"response":"1","message":{"content":"Explanation"}})
    client.complete("x = ",4)
    client.assist("x = 1","Explain")
    assert ("/api/generate",{"model":COMPLETION_MODEL,"keep_alive":0,"stream":False}) in calls
    assert calls[-1][1]["model"]==ASSISTANT_MODEL
    assert not any("30b" in str(payload) for _,payload in calls)


def test_focused_briefs_request_structured_bounded_output(monkeypatch):
    client,calls=fake_client(monkeypatch,{"message":{"content":"{}"}})
    client.assist("x = 1","Explain",structured=True)
    assert calls[-1][1]["format"]=="json"
    assert "summary" in calls[-1][1]["messages"][0]["content"]
    assert calls[-1][1]["options"]["num_ctx"]==2048


def test_cloud_model_is_rejected_before_generation(monkeypatch):
    client=LocalAI(); calls=[]
    def request(path,payload=None,*args,**kwargs):calls.append(path); return {"remote_host":"cloud.example"}
    monkeypatch.setattr(client,"request",request)
    with pytest.raises(ValueError,match="Cloud models"):
        client.complete("x = ",4)
    assert calls==["/api/show"]


def test_transport_is_fixed_loopback_and_cancellable(monkeypatch):
    seen={}
    class Response:
        status=200
        def read(self,size):return b'{"models":[]}'
    class Connection:
        sock=None
        def __init__(self,host,port,timeout):seen.update(host=host,port=port)
        def request(self,*args):seen["request"]=args
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr("changelens.local_ai.http.client.HTTPConnection",Connection)
    monkeypatch.setenv("HTTP_PROXY","http://external.example:8080")
    assert LocalAI().models()==set()
    assert seen["host"]=="127.0.0.1" and seen["port"]==11434
    stop=Event(); stop.set()
    with pytest.raises(Cancelled):LocalAI().models(stop)


def test_cancellation_interrupts_a_waiting_local_response(monkeypatch):
    import threading
    released=Event(); reading=Event(); cancelled=Event(); errors=[]
    class Sock:
        def shutdown(self,mode):released.set()
    class Response:
        status=200
        def read(self,size):reading.set(); released.wait(3); raise OSError("closed")
    class Connection:
        def __init__(self,*args,**kwargs):self.sock=Sock()
        def request(self,*args):pass
        def getresponse(self):self.sock=None; return Response()
        def close(self):pass
    monkeypatch.setattr("changelens.local_ai.http.client.HTTPConnection",Connection)
    def run():
        try:LocalAI().request("/api/tags",cancel=cancelled)
        except Exception as exc:errors.append(exc)
    worker=threading.Thread(target=run); worker.start(); assert reading.wait(1)
    cancelled.set(); worker.join(1)
    assert not worker.is_alive() and isinstance(errors[0],Cancelled)


def test_completion_strips_duplicate_suffix_and_rejects_fences(monkeypatch):
    client,_=fake_client(monkeypatch,{"response":"value + 1\n\ndef other(): pass\n"})
    result=client.complete("return \n\ndef other(): pass\n",7)
    assert result["text"]=="value + 1"
    client,_=fake_client(monkeypatch,{"response":"```python\nx = 1\n```"})
    assert not client.complete("",0)["text"]


def test_ghost_completion_tab_escape_and_single_undo():
    app=QApplication.instance() or QApplication([]); editor=CodeEditor(); editor.show(); editor.activateWindow(); editor.setFocus(); app.processEvents()
    editor.set_code("def total(value):\n    return "); editor.moveCursor(QTextCursor.MoveOperation.End)
    assert editor.offer_ghost("value + 1\n")
    assert editor.toPlainText().endswith("return ")
    QTest.keyClick(editor,Qt.Key.Key_Tab)
    assert editor.toPlainText().endswith("return value + 1\n")
    editor.undo(); assert editor.toPlainText().endswith("return ")
    editor.offer_ghost("value"); QTest.keyClick(editor,Qt.Key.Key_Escape)
    assert not editor.ghost_text and editor.toPlainText().endswith("return ")
    editor.insertPlainText("value"); editor.moveCursor(QTextCursor.MoveOperation.Start)
    assert not editor.offer_ghost("bad overlay")
    editor.close(); app.processEvents()


def test_model_rewrite_is_only_a_preview_and_preserves_other_code(tmp_path):
    source="# header\ndef total(value):\n    temp = value + 1\n    return temp\n\ndef other():\n    return 'untouched'\n"
    target=tmp_path/"a.py"; target.write_text(source)
    snapshot=index_repository(tmp_path)
    answer=json.dumps({"code":"def total(value):\n    return value + 1\n","explanation":"Inline an unnecessary temporary."})
    patch=rewrite_patch(snapshot,snapshot.symbols["a.py:total"],answer)
    assert patch["operation"]=="ai_rewrite" and patch["tests"]=="not run"
    assert "def other():\n    return 'untouched'" in patch["files"][0]["after"]
    ast.parse(patch["files"][0]["after"])
    assert target.read_text()==source


@pytest.mark.parametrize("code",["def changed(value): return value", "def total(other): return other", "import os\ndef total(value): return value", "def total(value):\n    import os\n    return value"])
def test_rewrite_rejects_signature_changes_and_imports(tmp_path,code):
    (tmp_path/"a.py").write_text("def total(value): return value + 1\n")
    snapshot=index_repository(tmp_path)
    with pytest.raises(ValueError):rewrite_patch(snapshot,snapshot.symbols["a.py:total"],json.dumps({"code":code}))


def settled(app,window):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        app.processEvents()
        if window.worker is None and window.ai_worker is None:return
        time.sleep(.01)
    assert window.worker is None and window.ai_worker is None


def test_native_local_ai_completion_without_implicit_saving(tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"settings"))
    root=tmp_path/"project"; root.mkdir(); source="def total(value):\n    return value\n"; (root/"a.py").write_text(source)
    app=QApplication.instance() or QApplication([]); window=MainWindow(); window.show(); window.open_path(root); settled(app,window)
    monkeypatch.setattr(window.local_ai,"models",lambda cancel:{COMPLETION_MODEL,ASSISTANT_MODEL})
    monkeypatch.setattr(window.local_ai,"warm_up",lambda cancel:None)
    monkeypatch.setattr(window.local_ai,"complete",lambda *args:{"text":" + 1","seconds":.02,"model":COMPLETION_MODEL})
    window.connect_ai(); settled(app,window)
    assert window.ai_ready and window.assistant_ready
    window.navigate(0)
    editor=window.current_editor(); editor.moveCursor(QTextCursor.MoveOperation.End); editor.moveCursor(QTextCursor.MoveOperation.PreviousBlock); editor.moveCursor(QTextCursor.MoveOperation.EndOfBlock)
    window.activateWindow(); editor.setFocus(); app.processEvents(); window.request_ai_completion(); settled(app,window)
    assert editor.ghost_text==" + 1"
    QTest.keyClick(editor,Qt.Key.Key_Tab)
    assert "return value + 1" in editor.toPlainText() and (root/"a.py").read_text()==source
    editor.set_code(source); window.close(); app.processEvents()


def test_native_ai_rewrite_review_and_explicit_apply(tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"settings"))
    root=tmp_path/"project"; root.mkdir(); source="def total(value):\n    result = value + 1\n    return result\n"; (root/"a.py").write_text(source)
    app=QApplication.instance() or QApplication([]); window=MainWindow(); window.show(); window.open_path(root); settled(app,window)
    window.assistant_ready=True
    monkeypatch.setattr(window.local_ai,"assist",lambda *args,**kwargs:json.dumps({"code":"def total(value):\n    return value + 1\n","explanation":"Remove a temporary."}))
    window.suggest_rewrite(); settled(app,window)
    assert window.patch["operation"]=="ai_rewrite" and window.pages.currentIndex()==4
    assert not window.new_name.isVisible() and "Remove a temporary" in window.refactor_context.text()
    assert (root/"a.py").read_text()==source
    window.apply_patch(); settled(app,window)
    assert (root/"a.py").read_text()=="def total(value):\n    return value + 1\n"
    assert (tmp_path/"settings"/"ChangeLens"/"backups").is_dir()
    window.close(); app.processEvents()
