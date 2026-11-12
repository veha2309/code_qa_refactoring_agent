import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from changelens.architecture import review_architecture
from changelens.core import index_repository
from changelens.design_canvas import extracted_model
from changelens.design_diagrams import scopes
from changelens.lld_review import collect_evidence, pack_evidence, parse_notes
from changelens.local_ai import LocalAI


SOURCE = """class Ledger:
    def withdraw(self, balance, amount):
        if amount > balance:
            return None
        return balance - amount
"""
NOTE = {"category": "Branches and errors", "text": "An amount above the balance returns None.",
        "evidence": "E2:4"}


def ledger(tmp_path):
    (tmp_path / "ledger.py").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "unrelated.py").write_text("def outside(): return 77\n", encoding="utf-8")
    snapshot = index_repository(tmp_path)
    report = review_architecture(snapshot)
    model = extracted_model(report, "LLD", scopes(report, False)[0])
    focus = next(row["id"] for row in model["nodes"] if row["title"] == "Ledger")
    return snapshot, report, model, focus


def test_focused_evidence_and_exact_source_citations(tmp_path):
    snapshot, report, model, focus = ledger(tmp_path)
    visible = {row["id"] for row in model["nodes"]}
    excerpts = collect_evidence(snapshot, model, report["symbols"], visible, focus)
    prompt, evidence, count = pack_evidence(excerpts, model, focus, 1500)
    assert "E2:4 |             return None" in prompt and count == 2
    assert "return 77" not in prompt
    assert parse_notes(json.dumps({"notes": [NOTE]}), evidence) == [
        {"category": NOTE["category"], "text": NOTE["text"], "path": "ledger.py", "line": 4, "quote": "return None"},
    ]
    for edit in ({"evidence": "E99:4"}, {"evidence": "E2:77"}):
        with pytest.raises(ValueError, match="citation"):
            parse_notes(json.dumps({"notes": [{**NOTE, **edit}]}), evidence)
    with pytest.raises(ValueError, match="interpretation"):
        parse_notes(json.dumps({"notes": [{**NOTE, "text": "An amount above"}]}), evidence)
    (tmp_path / "ledger.py").write_text(SOURCE.replace("None", "False"), encoding="utf-8")
    with pytest.raises(ValueError, match="Saved source has changed"):
        collect_evidence(snapshot, model, report["symbols"], visible, focus)


def test_local_model_retries_bad_citations_with_same_bounded_source(tmp_path, monkeypatch):
    snapshot, report, model, focus = ledger(tmp_path)
    excerpts = collect_evidence(snapshot, model, report["symbols"], {focus}, focus)
    client = LocalAI()
    client.context_limit = 2048
    monkeypatch.setattr(client, "activate", lambda *args: None)
    calls = []

    def request(path, payload, cancel, timeout):
        calls.append(payload["messages"][1]["content"])
        assert path == "/api/chat"
        assert payload["options"]["num_ctx"] == 2048
        assert payload["format"]["required"] == ["notes"]
        note = {**NOTE, "evidence": "E99"} if len(calls) == 1 else NOTE
        return {"message": {"content": json.dumps({"notes": [note]})}}

    monkeypatch.setattr(client, "request", request)
    result, count = client.review_lld(excerpts, model, focus)
    assert count and result[0]["line"] == 4
    assert len(calls) == 2 and calls[0] == calls[1]


@pytest.mark.parametrize(("feature", "stale"), [(False, False), (True, False), (False, True)])
def test_lld_draft_previews_applies_and_undoes_model_notes(tmp_path, monkeypatch, feature, stale):
    from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPlainTextEdit, QPushButton
    from changelens.workbench import MainWindow
    from test_local_ai import settled

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "settings"))
    monkeypatch.setenv("CHANGELENS_TEST_NO_AI", "1")
    root = tmp_path / "project"
    root.mkdir()
    if feature:
        source = ("from fastapi import FastAPI\napp = FastAPI()\n@app.get('/health')\n"
                  "def health():\n    return {'ok': True}\n")
        path, number = "api.py", 5
        (root / path).write_text(source, encoding="utf-8")
    else:
        snapshot, report, model, focus = ledger(root)
        path, number = "ledger.py", 4
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    try:
        window.open_path(root)
        settled(app, window)
        window.navigate(8)
        settled(app, window)
        view = window.architecture_view
        if feature:
            assert view.lld_review.isHidden()
            view.flows.features.setCurrentRow(0)
            focus = "handler0"
        else:
            view.tabs.setCurrentIndex(3)
            assert view.lld_review.isHidden()
            view.diagram_choice.setCurrentIndex(1)
        canvas = view.active_canvas()
        canvas.nodes[focus].setSelected(True)
        assert not view.lld_review.isHidden()
        before = canvas.model
        monkeypatch.setattr(window.local_ai, "activate", lambda *args: None)

        def request(endpoint, payload, cancel, timeout):
            assert endpoint == "/api/chat"
            assert f"{number} | " in payload["messages"][1]["content"]
            note = {**NOTE, "text": "Explain the returned value.",
                    "evidence": f"E1:{number}" if feature else NOTE["evidence"]}
            return {"message": {"content": json.dumps({"notes": [note]})}}

        monkeypatch.setattr(window.local_ai, "request", request)
        view.lld_review.click()
        settled(app, window)
        dialog = next(child for child in window.findChildren(QDialog) if child.isVisible())
        assert f"{path}:{number}" in dialog.findChild(QPlainTextEdit).toPlainText()
        assert canvas.model is before and window.pages.currentWidget() is view
        add = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Add notes to diagram")
        if stale:
            (root / path).write_text(SOURCE.replace("None", "False"), encoding="utf-8")
        add.click()
        settled(app, window)
        if stale:
            assert "Repository changed" in dialog.findChild(QLabel).text()
            assert canvas.model == before
            dialog.close()
            return
        assert window.pages.currentWidget() is view
        assert canvas.model["edges"] == before["edges"]
        assert canvas.model["nodes"][:-1] == before["nodes"]
        note = canvas.model["nodes"][-1]
        assert note["model_notes"][0]["line"] == number
        canvas.write_svg(tmp_path / "lld.svg")
        assert "AI INTERPRETATION" in (tmp_path / "lld.svg").read_text(encoding="utf-8")
        canvas.history.undo()
        assert canvas.model == before
        canvas.history.redo()
        assert canvas.model["nodes"][-1] == note
    finally:
        window.close()
        app.processEvents()
