"""Native UI for optional local completion and reviewable model suggestions."""
from functools import partial
import json
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QComboBox
from .brief import BriefView, brief_markdown

from .core import app_dir, index_repository, parse_file
from .jobs import Worker
from .local_ai import LocalAI, COMPLETION_MODEL, ASSISTANT_MODEL, rewrite_patch, presentation_check
from .languages import language_for,is_source,NAMES
from .refactoring import linked_tests


def build_rewrite_proposal(client,snapshot,symbol,goal,focus_offset,cancel,finding=None):
    from .model_context import related_context

    boundary = " Return the supplied declaration fragment. Preserve its signature and modifiers. Leave surrounding exports and declarations alone. Add no dependencies."
    if finding:
        instruction = "Fix the reported behavior so it matches the quoted expectation. Explain the edit in one plain-language sentence." + boundary
        context = json.dumps({"expected behavior": finding["basis"], "current code": finding["witness"],
                              "reported issue": finding["detail"]}, ensure_ascii=False)
    else:
        instruction = ("Requested improvement: "+goal+". " if goal else "") + "Suggest a small readability improvement with unchanged behavior." + boundary
        context = related_context(snapshot,symbol,budget=client.related_context_budget())
    options = {"fix": True} if finding else {}
    answer = client.assist(symbol.source,instruction,context=context,rewrite=True,cancel=cancel,
                           language=NAMES[language_for(symbol.path)],focus_offset=focus_offset,**options)
    patch = rewrite_patch(snapshot,symbol,answer)
    patch["linked_tests"] = linked_tests(snapshot,[symbol.id],cancel)
    if finding:
        patch["finding_title"] = finding["title"]
        patch["fix_focus"] = {"review": True, "path": symbol.path, "line": symbol.start}
    return patch


class AIWorkbench:
    def open_brief(self):
        self.navigate(7)
        if not self.assistant_ready:self.ai_settings_toggle.setChecked(True);self.ai_settings.show()

    def build_ai(self):
        self.local_ai=LocalAI(); self.ai_worker=None; self.ai_ready=False; self.assistant_ready=False
        self.pending_ai_completion=False; self.ai_job_kind=None;self.pending_model_action=None
        page=QWidget(); outer=QHBoxLayout(page); outer.setContentsMargins(16,16,16,16)
        content=QWidget(); content.setMaximumWidth(1000); outer.addStretch(); outer.addWidget(content,1); outer.addStretch()
        layout=QVBoxLayout(content); layout.setContentsMargins(0,0,0,0); layout.setSpacing(14)
        top=QHBoxLayout()
        title=QLabel("Code notes");self.ai_heading=title; title.setObjectName("lensTitle"); top.addWidget(title,1)
        self.ai_settings_toggle=QPushButton("Model settings"); self.ai_settings_toggle.setCheckable(True); top.addWidget(self.ai_settings_toggle); layout.addLayout(top)
        self.ai_context_label=QLabel("Focus a node in the Lens, or place the cursor inside a function."); self.ai_context_label.setObjectName("briefContext"); self.ai_context_label.setWordWrap(True); layout.addWidget(self.ai_context_label)
        self.ai_status=QLabel("Generated explanations may be incorrect. Use Lens to inspect dependency evidence.")
        self.ai_status.setWordWrap(True); self.ai_status.setObjectName("muted"); layout.addWidget(self.ai_status)
        self.ai_language_status=QLabel('Ollama supports review and rewrite for every indexed source language.');self.ai_language_status.setWordWrap(True);layout.addWidget(self.ai_language_status)
        self.ai_settings=QFrame(); self.ai_settings.setObjectName("modelSettings"); settings=QVBoxLayout(self.ai_settings)
        description=QLabel("Local models · 16 GB RAM / 4 GB GPU preset\n1.5B autocomplete · optional 3B briefs and rewrites · one model active at a time")
        description.setObjectName("muted"); settings.addWidget(description)
        context_row=QHBoxLayout();context_row.addWidget(QLabel('Maximum context'))
        self.context_size=QComboBox()
        for label,size in [('2K · compact',2048),('4K · balanced',4096),('8K · more memory',8192)]:self.context_size.addItem(label,size)
        self.context_size.setCurrentIndex(1);self.context_size.currentIndexChanged.connect(self.context_changed);context_row.addWidget(self.context_size);settings.addLayout(context_row)
        row=QHBoxLayout()
        self.ai_connect=QPushButton("Connect models"); self.ai_connect.clicked.connect(self.connect_ai); row.addWidget(self.ai_connect)
        self.ai_download=QPushButton("Prepare autocomplete (~1 GB)")
        self.ai_download.clicked.connect(lambda:self.download_ai(COMPLETION_MODEL)); row.addWidget(self.ai_download)
        self.assistant_download=QPushButton("Prepare briefs (~2 GB)")
        self.assistant_download.clicked.connect(lambda:self.download_ai(ASSISTANT_MODEL)); row.addWidget(self.assistant_download)
        row.addStretch(); settings.addLayout(row)
        self.ai_readiness=QPushButton("Check presentation readiness"); self.ai_readiness.clicked.connect(self.check_presentation); settings.addWidget(self.ai_readiness)
        self.ai_settings_toggle.toggled.connect(self.ai_settings.setVisible); self.ai_settings.hide(); layout.addWidget(self.ai_settings)
        actions=QHBoxLayout(); self.ai_explain=QPushButton("Explain focused code"); self.ai_explain.clicked.connect(self.explain_code); actions.addWidget(self.ai_explain)
        self.ai_rewrite=QPushButton("Suggest a change"); self.ai_rewrite.clicked.connect(self.suggest_rewrite); actions.addWidget(self.ai_rewrite)
        self.ai_review=QPushButton('Review focused code');self.ai_review.clicked.connect(self.review_code);actions.addWidget(self.ai_review)
        self.ai_cancel=QPushButton("Cancel"); self.ai_cancel.clicked.connect(self.cancel_ai); self.ai_cancel.hide(); actions.addWidget(self.ai_cancel)
        actions.addStretch(); layout.addLayout(actions)
        self.ai_answer=BriefView(); self.ai_answer.setPlaceholderText("Select code in the editor or a node in Lens, then choose Explain focused code."); layout.addWidget(self.ai_answer,1)
        self.pages.addWidget(page)

    def context_changed(self,*args):
        self.local_ai.context_limit=self.context_size.currentData()
        path=app_dir()/'local-ai.json'
        try:value=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError):value={}
        value['context_limit']=self.local_ai.context_limit;path.write_text(json.dumps(value),encoding='utf-8')

    def context_note(self):
        record=self.local_ai.last_context_report
        if not record:return ''
        ranges=', '.join(f"{a}–{b}" for a,b in record.get('included_lines',[]))
        return f" Context: {record['window']} tokens; ~{record['estimated_input']} estimated input; {record['reserved_output']} reserved output; lines {ranges} of the focused declaration; "+('omitted code excluded.' if record['omitted'] else 'complete focus included.')

    def initialize_ai(self):
        import os
        if os.environ.get("CHANGELENS_TEST_NO_AI")=="1":return
        try:enabled=json.loads((app_dir()/"local-ai.json").read_text(encoding="utf-8")).get("enabled",True)
        except (OSError,ValueError):enabled=True
        try:
            saved=json.loads((app_dir()/'local-ai.json').read_text(encoding='utf-8')).get('context_limit',4096)
            index=self.context_size.findData(saved)
            if index>=0:self.context_size.setCurrentIndex(index)
        except (OSError,ValueError):pass
        if enabled:QTimer.singleShot(0,self.connect_ai)

    def model_focus(self):
        editor=self.current_editor();document=self.current_document()
        return (self.snapshot.root if self.snapshot else None,str(document.path) if document else None,
            editor.toPlainText() if editor else None,editor.textCursor().position() if editor else None,editor.textCursor().anchor() if editor else None)

    def require_assistant(self,callback):
        if self.assistant_ready and self.ai_worker is None:return True
        self.pending_model_action=(callback,self.model_focus());self.pending_ai_completion=False
        if self.ai_worker:
            if self.ai_job_kind=='completion':self.ai_worker.cancel.set()
        else:self.connect_ai()
        self.ai_status.setText('Connecting to the installed Ollama review model; your requested action will continue automatically.')
        return False

    def update_ai_language(self):
        if not hasattr(self,'ai_language_status'):return
        document=self.current_document();language=NAMES.get(language_for(document.path),'Source') if document else 'All indexed languages'
        self.ai_language_status.setText(language+' · local model findings, explanations and reviewed rewrites · '+('Ollama model detected' if self.assistant_ready else 'Ollama connection checked on request'))

    def start_ai(self,task,callback,message,kind="assistant",on_error=None):
        if self.ai_worker:return
        if kind!="completion":self.ai_status.setText(message);self.ai_status.show()
        self.ai_cancel.show()
        for button in (self.ai_connect,self.ai_download,self.assistant_download,self.ai_explain,self.ai_rewrite,self.ai_review,self.ai_readiness):button.setEnabled(False)
        worker=Worker(task,self); self.ai_worker=worker; self.ai_job_kind=kind; result={};self.refresh_actions()
        epoch=getattr(self,'_workspace_epoch',0)
        worker.done.connect(lambda value:result.update(value=value)); worker.failed.connect(lambda error:result.update(error=error))
        def finished():
            self.ai_worker=None; self.ai_job_kind=None; worker.deleteLater(); self.ai_cancel.hide()
            for button in (self.ai_connect,self.ai_download,self.assistant_download,self.ai_explain,self.ai_rewrite,self.ai_review,self.ai_readiness):button.setEnabled(True)
            if epoch!=getattr(self,'_workspace_epoch',0) and kind!='connect':
                if kind=="lld_review" and on_error:on_error("The project changed. Open a new preview in Design.")
                self.refresh_actions()
                return
            if worker.cancel.is_set() and kind in {"qa_review","inline_rewrite","lld_review"}:
                result["error"]="Model review cancelled." if kind=="qa_review" else "Model request cancelled."
            if "error" in result:
                message=result['error']
                if kind=='rewrite' and 'did not propose a change' in message:
                    message=('The model did not propose a fix. Preview again or open the code to edit it.'
                             if getattr(self,'qa_fix_request',None)
                             else 'No new improvement returned. Change the focus or regenerate.')
                if kind=='rewrite':
                    self.patch=None;self.patch_list.clear();self.diff_view.clear();self.update_result_state()
                    self.refactor_context.setText(message)
                self.ai_status.setText(message);self.ai_status.show(); self.status.setText(message[:140])
                if on_error:on_error(message)
            else:
                try:
                    callback(result.get("value"))
                    if kind not in {"completion","qa_review","inline_rewrite","lld_review"}:self.ai_status.setText(self.ai_status.text()+self.context_note());self.ai_status.show()
                except Exception as exc:
                    self.ai_status.setText(str(exc));self.status.setText(str(exc)[:140])
                    if on_error:on_error(str(exc))
                    if kind=='rewrite':
                        self.patch=None;self.patch_list.clear();self.diff_view.clear();self.update_result_state()
                        self.refactor_context.setText(str(exc))
            pending=self.pending_model_action;self.pending_model_action=None
            if pending:
                if self.assistant_ready and pending[1]==self.model_focus():
                    try:pending[0]()
                    except Exception as exc:self.ai_status.setText(str(exc))
                elif pending[1]!=self.model_focus():self.ai_status.setText('Code focus changed while connecting; request the model action again for the current code.')
                elif 'error' in result:self.open_brief();self.ai_status.setText(result['error']+' The requested action was not run.')
                else:self.open_brief();self.ai_status.setText('Ollama review model was not detected. Connect the local server or prepare '+self.local_ai.assistant_model+'.')
            elif self.pending_ai_completion and self.ai_worker is None:
                self.pending_ai_completion=False; QTimer.singleShot(0,self.request_ai_completion)
            self.refresh_actions()
        worker.finished.connect(finished); worker.start()

    def cancel_ai(self):
        self.pending_ai_completion=False;self.pending_model_action=None
        if self.ai_worker:self.ai_worker.cancel.set(); self.ai_status.setText("Cancelling local model request…")

    def connect_ai(self):
        def prepare(cancel,progress):
            return self.local_ai.models(cancel)
        def ready(models):
            self.ai_ready=COMPLETION_MODEL in models; self.assistant_ready=ASSISTANT_MODEL in models
            for editor in self.documents:editor.ai_enabled=self.ai_ready
            (app_dir()/"local-ai.json").write_text(json.dumps({"enabled":True,"context_limit":self.local_ai.context_limit}),encoding="utf-8")
            self.ai_status.setText(f"Autocomplete: {'ready' if self.ai_ready else 'download needed'} · Assistant: {'ready' if self.assistant_ready else 'optional download needed'}. All inference stays on this computer.")
            self.ai_button.setText("Brief")
            if self.assistant_ready:self.ai_settings_toggle.setChecked(False)
            self.update_ai_language()
        self.start_ai(prepare,ready,"Checking installed Ollama models; no download or model loading is required…",kind='connect')

    def download_ai(self,model):
        def downloaded(result):self.ai_status.setText("Model downloaded. Checking availability…"); self.connect_ai()
        self.start_ai(lambda cancel,progress:self.local_ai.request("/api/pull",{"model":model,"stream":False},cancel,timeout=900),downloaded,"Downloading "+model+". This requires internet once; the model stays on this computer.")

    def prepare_ai_context(self,symbol,budget=None):
        snapshot=self.snapshot
        if not snapshot or not symbol:return lambda: ""
        from .model_context import related_context
        report=self.architecture_view.report or {}
        if budget is None:budget=self.local_ai.related_context_budget()
        flows=report.get('feature_flows') if report.get('snapshot_id')==snapshot.id else None
        return partial(related_context,snapshot,symbol,flows,budget=budget)

    def ai_selection(self):
        editor=self.current_editor(); document=self.current_document()
        if not editor or not document or not is_source(document.path):raise ValueError("Open a supported source file first.")
        line=editor.textCursor().blockNumber()+1; relative=document.path.relative_to(Path(self.snapshot.root)).as_posix()
        key=editor.document().revision()
        cached=getattr(editor,'_ai_parse_cache',None)
        if cached and cached[0]==key:symbols=cached[1]
        else:
            try:symbols=parse_file(relative,editor.toPlainText())[0]
            except SyntaxError:symbols=[]
            editor._ai_parse_cache=(key,symbols)
        matches=[s for s in symbols if s.start<=line<=s.end and s.kind in {"function","async_function"}]
        symbol=min(matches,key=lambda s:s.end-s.start) if matches else None
        selected=editor.textCursor().selectedText().replace("\u2029","\n")
        return editor,document,symbol,selected or (symbol.source if symbol else editor.toPlainText())

    def request_ai_completion(self):
        if not self.ai_ready:return
        if self.ai_worker:
            self.pending_ai_completion=True
            if self.ai_job_kind=="completion":self.ai_worker.cancel.set()
            return
        editor=self.current_editor(); document=self.current_document()
        if not editor or not document or not is_source(document.path) or editor.isReadOnly() or not editor.hasFocus() or editor.textCursor().hasSelection():return
        cursor=editor.textCursor()
        if cursor.block().text().encode("utf-16-le")[cursor.positionInBlock()*2:].decode("utf-16-le").strip():return
        code=editor.toPlainText(); position=editor.textCursor().position(); offset=editor.code_offset();epoch=editor.completion_epoch
        try:_,_,symbol,_=self.ai_selection()
        except ValueError:symbol=None
        pack_context=self.prepare_ai_context(symbol,budget=180)
        def completed(result):
            if self.current_editor() is editor and editor.toPlainText()==code and editor.textCursor().position()==position and editor.completion_epoch==epoch:
                shown=editor.offer_ghost(result["text"])
                if shown:self.status.setText("Local AI suggestion · Tab to accept · Escape to dismiss")
        language=language_for(document.path)
        self.start_ai(lambda cancel,progress:self.local_ai.complete(code,offset,pack_context(),cancel,language),completed,"Generating a local code completion…",kind="completion")

    def explain_code(self):
        if not self.require_assistant(self.explain_code):return
        try:editor,document,symbol,code=self.ai_selection()
        except ValueError as exc:self.ai_status.setText(str(exc)); return
        if symbol is None and not editor.textCursor().hasSelection():
            self.navigate(6); self.status.setText("Choose a function in the Lens or select code to explain."); return
        self.ai_context_label.setText((symbol.qualname if symbol else "Selected code")+" / "+document.path.name)
        self.navigate(7)
        self.ai_answer.clear()
        def explained(answer):self.ai_answer.setPlainText(brief_markdown(answer)); self.ai_status.setText("Local explanation ready. This is model interpretation, not execution evidence.")
        pack_context=self.prepare_ai_context(symbol)
        language=NAMES[language_for(document.path)]
        focus_offset=0 if editor.textCursor().hasSelection() or not symbol else max(0,editor.code_offset()-sum(len(row) for row in editor.toPlainText().splitlines(True)[:symbol.start-1]))
        self.start_ai(lambda cancel,progress:self.local_ai.assist(code,"Explain only this focused code. Do not invent existing tests or claim execution results.",pack_context(),cancel=cancel,structured=True,language=language,focus_offset=focus_offset),explained,"Reading the focused code locally…")

    def review_code(self):
        if not self.require_assistant(self.review_code):return
        try:editor,document,symbol,code=self.ai_selection()
        except ValueError as exc:self.notify(str(exc),True);return
        language=NAMES[language_for(document.path)];root=self.snapshot.root;buffer=editor.toPlainText();snapshot_id=self.snapshot.id
        pack_context=self.prepare_ai_context(symbol)
        self.ai_context_label.setText('Model findings · '+language+' · '+document.path.name);self.navigate(7);self.ai_answer.clear()
        def reviewed(answer):
            if not self.snapshot or self.snapshot.root!=root or editor not in self.documents or editor.toPlainText()!=buffer:
                self.ai_status.setText('Source changed during review; outdated model findings were discarded.');return
            self.last_model_review={'snapshot_id':snapshot_id,'path':str(document.path),'language':language,'answer':answer,'classification':'model interpretation; not execution evidence'}
            self.ai_answer.setPlainText(brief_markdown(answer));self.ai_status.setText('Model findings for '+language+' · proposals, not confirmed defects · tests not run.')
        self.start_ai(lambda cancel,progress:self.local_ai.assist(code,'Review the supplied code for concrete potential defects and useful refactoring. Summarize the strongest supported finding; identify uncertainty and up to three verification steps. Cite identifiers in the excerpt. Do not invent relationships, APIs, test results or a Python-only restriction. Return a no-finding summary if evidence is insufficient.',pack_context(),cancel=cancel,structured=True,language=language),reviewed,'Reviewing '+language+' source locally…')

    def review_project_model(self):
        if not self.require_assistant(self.review_project_model):return
        report=self.architecture_view.report;snapshot=getattr(self,'architecture_snapshot',None)
        if not report or not snapshot:self.notify('Generate a saved-source architecture review first.');return
        from .model_context import fit_text
        from .core import ensure_fresh
        from .languages import NAMES
        root=snapshot.root;key=report['snapshot_id'];modules=sorted(report['modules'],key=lambda m:(-(len(m['incoming'])+len(m['outgoing'])),m['path']))[:4]
        sources=[];rows=[]
        for module in modules:
            candidates=[s for s in snapshot.symbols.values() if s.path==module['path'] and s.kind in {'function','async_function'}]
            if not candidates:continue
            symbol=min(candidates,key=lambda s:s.start);sources.append({'path':symbol.path,'start':symbol.start,'end':symbol.end})
            rows.append(symbol.path+':'+str(symbol.start)+'–'+str(symbol.end)+' (bounded excerpt)\n'+fit_text(symbol.source,220))
        if not rows:self.notify('No indexed declarations are available for a source-backed model review.');return
        language=', '.join(NAMES.get(k,k) for k in snapshot.profile.get('languages',{}))
        code='Sampled project sources; omitted files were not reviewed.\n\n'+'\n\n'.join(rows)
        context='Project languages: '+language+'\nFramework declarations: '+', '.join(v['name'] for v in report['framework_hints'])
        self.ai_context_label.setText('Model findings · sampled project sources');self.navigate(7);self.ai_answer.clear()
        def task(cancel,progress):
            ensure_fresh(snapshot)
            answer=self.local_ai.assist(code,'Review only these sampled source excerpts for concrete potential defects or useful refactoring. Cite identifiers and source paths. Distinguish source evidence from model interpretation. Do not claim the entire project was reviewed, tests ran, or runtime connections were proven.',context,cancel=cancel,structured=True,language=language)
            ensure_fresh(snapshot);return answer
        def reviewed(answer):
            if not self.snapshot or self.snapshot.root!=root or (self.architecture_view.report or {}).get('snapshot_id')!=key:
                self.ai_status.setText('Project changed; the previous model findings were discarded.');return
            self.last_model_review={'snapshot_id':key,'scope':'sampled project sources','sources':sources,'language':language,'answer':answer,'classification':'model interpretation'}
            self.ai_answer.setPlainText(brief_markdown(answer));self.ai_status.setText('Model findings from '+str(len(sources))+' sampled declarations · omitted files not reviewed · tests not run.')
        self.start_ai(task,reviewed,'Reviewing bounded project excerpts locally…')

    def review_lld(self):
        from uuid import uuid4
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout
        from .core import ensure_fresh
        from .design_canvas import DesignNode, extracted_model
        from .feature_flows import design_model
        from .lld_review import collect_evidence

        view = self.architecture_view
        canvas = view.active_canvas()
        draft = canvas.model
        report = view.report
        snapshot = getattr(self, "architecture_snapshot", None)
        workspace_snapshot = self.snapshot
        if not draft or draft["level"] != "LLD" or not report or not snapshot:
            return
        if (not workspace_snapshot or workspace_snapshot.root != snapshot.root
                or snapshot.id != report["snapshot_id"] or snapshot.id != draft["snapshot_id"]):
            self.notify("Refresh the saved-source Design review before requesting LLD notes.", True)
            return
        if self.ai_worker:
            self.notify("A local model request is running. Try again when it finishes.", True)
            return

        if canvas is view.flows.canvas:
            flow = view.flows.by_id.get(view.flows.current_flow)
            base = design_model(report, flow)
            scope = flow["title"] if flow else "Feature flow"
        else:
            _, level, scope, page, include_aux = view.design_key
            base = extracted_model(report, level, scope, page, include_aux)
        if any(base[key] != draft[key] for key in ("level", "scope", "page")):
            self.notify("Open the matching source diagram before requesting notes for this draft.", True)
            return

        visible = {row["id"] for row in draft["nodes"]}
        cards = {row["id"]: row for row in base["nodes"]}
        selection = [item.record["id"] for item in canvas.scene.selectedItems()
                     if isinstance(item, DesignNode)]
        focus = selection[0] if len(selection) == 1 else None
        if focus and (focus not in cards or cards[focus].get("path") not in snapshot.hashes
                      or cards[focus]["kind"] in {"Coverage gap", "Continuation"}):
            self.notify("Select a card with saved source, or clear the selection to review the page.", True)
            return
        title = cards[focus]["title"] if focus else str(scope)

        dialog = QDialog(self)
        dialog.setWindowTitle("Suggest LLD notes")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.resize(670, 415)
        layout = QVBoxLayout(dialog)
        status = QLabel(f"Reviewing {title} with {self.local_ai.assistant_model}…")
        status.setTextFormat(Qt.TextFormat.PlainText)
        status.setWordWrap(True)
        layout.addWidget(status)
        preview = QPlainTextEdit()
        preview.setReadOnly(True)
        layout.addWidget(preview, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        add = buttons.addButton("Add notes to diagram", QDialogButtonBox.ButtonRole.ActionRole)
        add.setEnabled(False)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        active = True
        worker = None
        notes = []

        def still_current():
            return (self.pages.currentWidget() is view and view.active_canvas() is canvas
                    and view.report is report and canvas.model is draft
                    and self.architecture_snapshot is snapshot and self.snapshot
                    and self.snapshot.id in {snapshot.id, workspace_snapshot.id})

        def failed(message):
            if active:
                status.setText(message)
                add.setEnabled(False)

        def finished(_):
            nonlocal active
            active = False
            if worker is not None and self.ai_worker is worker:
                worker.cancel.set()

        def task(cancel, progress):
            ensure_fresh(snapshot, cancel)
            excerpts = collect_evidence(snapshot, base, report["symbols"], visible, focus, cancel)
            if not excerpts:
                raise ValueError("No saved source excerpts are available for this diagram.")
            result = self.local_ai.review_lld(excerpts, base, focus, cancel)
            ensure_fresh(snapshot, cancel)
            return result

        def ready(result):
            if not active:
                return
            if not still_current():
                failed("The diagram changed during generation. Open a new preview for the current diagram.")
                return
            found, source_count = result
            notes[:] = found
            if not found:
                failed(f"The model found no useful notes in {source_count} saved-source excerpts.")
                return
            status.setText(f"AI interpretation from {source_count} saved-source excerpts. Review each claim against its cited code.")
            preview.setPlainText("\n\n".join(
                f'{row["category"]}\n{row["text"]}\n{row["path"]}:{row["line"]}\n{row["quote"]}'
                for row in found
            ))
            add.setEnabled(len(draft["nodes"]) < 200)
            if not add.isEnabled():
                status.setText("The diagram has reached the 200-card limit. The preview can be copied.")

        def commit_notes(_):
            if not active:
                return
            if not still_current():
                failed("The diagram changed. Open a new preview for the current diagram.")
                return
            note_id = str(uuid4())
            card = {
                "id": note_id, "title": "AI design notes · " + title[:160], "kind": "note",
                "origin": "user", "fields": [],
                "path": notes[0]["path"], "line": notes[0]["line"],
                "x": min(999900, max(row["x"] for row in draft["nodes"]) + 430),
                "y": next((row["y"] for row in draft["nodes"] if row["id"] == focus), 0),
                "operations": [f'{row["category"]} · {row["text"]} [{row["path"]}:{row["line"]}]' for row in notes],
                "model_snapshot_id": snapshot.id, "model_notes": notes.copy(),
            }
            canvas.transaction("Add AI design notes", lambda model: model["nodes"].append(card))
            canvas.view.centerOn(canvas.nodes[note_id])
            dialog.accept()
            self.notify("AI design notes added to the diagram draft.")

        def start(task, callback, message):
            nonlocal worker
            self.start_ai(task, callback, message, "lld_review", failed)
            worker = self.ai_worker

        def apply_notes():
            if not notes or not still_current():
                failed("The diagram changed. Open a new preview for the current diagram.")
                return
            if self.ai_worker:
                status.setText("A local model request is running. Try again when it finishes.")
                return
            add.setEnabled(False)
            status.setText("Checking the saved-source snapshot…")
            start(lambda cancel, progress: ensure_fresh(snapshot, cancel), commit_notes,
                  "Checking the saved-source snapshot…")

        add.clicked.connect(apply_notes)
        start(task, ready, "Generating LLD notes with the local model…")
        dialog.finished.connect(finished)
        dialog.open()

    def explain_impact(self,sid):
        if not self.snapshot or sid not in self.snapshot.symbols:return
        self.select_symbol(sid)
        if not self.require_assistant(lambda:self.explain_impact(sid)):return
        symbol=self.snapshot.symbols[sid]
        row=self.lens_view.rows.get(sid) or (next((row for row in self.report["impact"] if row["symbol"]==sid),None) if self.report else None)
        context="\n".join(f"{edge['caller']} -> {edge['callee']}; line {edge['line']}; {edge['kind']}; {edge['expression']}" for edge in (row or {}).get("evidence",[]))[:700]
        self.ai_context_label.setText("Impact path / "+sid); self.navigate(7)
        self.ai_answer.clear()
        def explained(answer):self.ai_answer.setPlainText(brief_markdown(answer)); self.ai_status.setText("Model brief based on the displayed path. Inspect the Lens for the underlying recorded evidence.")
        language=NAMES[language_for(symbol.path)]
        self.start_ai(lambda cancel,progress:self.local_ai.assist(symbol.source,"Explain the supplied impact path briefly. Line numbers identify reference locations, not necessarily definition lines. Distinguish resolved links from inferences. Do not add relationships or claim tests ran.",context,cancel=cancel,structured=True,language=language),explained,"Preparing a brief from the selected evidence path…")

    def check_presentation(self):
        if not self.ai_ready:self.ai_status.setText("Prepare and enable the autocomplete model first."); return
        def checked(report):
            output=app_dir()/"reports"/"presentation_readiness.json"; output.parent.mkdir(parents=True,exist_ok=True)
            output.write_text(json.dumps(report,indent=2),encoding="utf-8")
            rows=[f"{row['case']}: {row['seconds']:.2f}s · syntax {'valid' if row['syntax_valid'] else 'invalid'}" for row in report["cases"]]
            self.ai_answer.setPlainText("Measured on this computer\n\n"+"\n".join(rows)+"\n\n"+report["limitations"]+"\n\nReport: "+str(output))
            self.ai_status.setText("Readiness check complete. Generated examples were checked for syntax and were not executed.")
            self.ai_settings_toggle.setChecked(False)
        self.start_ai(lambda cancel,progress:presentation_check(self.local_ai,cancel),checked,"Measuring three local completions on this computer…")

    def suggest_rewrite(self, *, fix=None):
        if self.worker:return
        if fix:
            if self.report_stale or not self.snapshot or self.snapshot.id != fix["snapshot"]:
                self.notify("The code changed. Review it again before previewing a fix.", True)
                return
        if not self.refactor_uses_saved_source():return
        callback = (lambda: self.suggest_rewrite(fix=fix)) if fix else self.suggest_rewrite
        if not self.require_assistant(callback):return
        self.check_timer.stop();self.preview_timer.stop();self.pending_check=False
        try:editor,document,_,_=self.ai_selection()
        except ValueError as exc:self.ai_status.setText(str(exc)); return
        root=Path(self.snapshot.root); relative=document.path.relative_to(root).as_posix(); line=editor.textCursor().blockNumber()+1;cursor_offset=editor.code_offset()
        saved_text,digest=document.text,document.digest
        chosen = getattr(self,"refactor_ai_target",None)
        target_id = chosen[1] if chosen and chosen[0] is editor and chosen[2] == line else None
        goal=self.model_instruction.text().strip()[:600]
        self.operation.setCurrentIndex(self.operation.findData('ai_rewrite'));self.new_name.setText('ai_suggestion')
        self.qa_fix_request = fix
        self.patch=None;self.patch_list.clear();self.diff_view.clear();self.update_result_state();self.navigate(4)
        self.model_instruction.setVisible(not fix)
        self.preview_button.setText("Preview fix again" if fix else "Preview improvement")
        self.refactor_context.setText('Preparing a fix for “'+fix["finding"]["title"]+'”…' if fix
                                      else 'Preparing a local proposal… Review its diff and validation before applying.')
        def task(cancel,progress):
            snapshot=index_repository(root,cancel,progress)
            if snapshot.hashes.get(relative)!=digest:
                raise ValueError("The saved file changed on disk. Refresh the editor and choose the function again.")
            if fix:
                symbol = snapshot.symbols.get(fix["symbol"])
                if snapshot.id != fix["snapshot"] or not symbol or symbol.path != relative:
                    raise ValueError("The code changed or another file is open. Return to Review to preview the fix.")
            else:
                matches=[s for s in snapshot.symbols.values() if s.path==relative and s.start<=line<=s.end and s.kind in {"function","async_function"}]
                if not matches:raise ValueError("Place the cursor inside the function to improve.")
                if target_id:
                    symbol=next((s for s in matches if s.id==target_id),None)
                    if not symbol:raise ValueError("The selected function moved. Choose it again before previewing.")
                else:symbol=min(matches,key=lambda s:s.end-s.start)
            lines=saved_text.splitlines(True)
            if fix:
                finding = fix["finding"]
                focus_offset = sum(len(row) for row in lines[symbol.start-1:finding["line"]-1])
            else:
                finding = None
                base=sum(len(row) for row in lines[:symbol.start-1])
                focus_offset = max(0,cursor_offset-base)
            return snapshot,build_rewrite_proposal(self.local_ai,snapshot,symbol,goal,focus_offset,cancel,finding)
        def suggested(result):
            if not self.snapshot or result[0].root!=self.snapshot.root:raise ValueError("Workspace changed; the previous AI suggestion was discarded.")
            if fix and self.qa_fix_request is not fix:raise ValueError("The selected operation changed. Return to Review to preview the fix.")
            if (self.operation.currentData()!="ai_rewrite" or self.current_editor() is not editor
                    or editor.document().isModified() or document.digest!=digest):
                message="The refactoring target changed. Preview the improvement again."
                self.ai_status.setText(message)
                self.update_refactor_context()
                self.notify(message)
                return
            result[1]["model_context"]=dict(self.local_ai.last_context_report)
            result[1]["explanation"]+=self.context_note()
            self.ai_answer.setPlainText(result[1]["explanation"]); self.previewed(result)
            self.ai_status.setText("Suggested diff ready. Syntax checked; tests not run. Review before applying.")
        self.start_ai(task,suggested,"Preparing a reviewable local-model suggestion…",kind='rewrite')
