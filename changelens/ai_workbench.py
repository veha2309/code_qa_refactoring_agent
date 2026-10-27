"""Native UI for optional local completion and reviewable model suggestions."""
import json
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from .brief import BriefView, brief_markdown

from .core import app_dir, index_repository, parse_file
from .jobs import Worker
from .local_ai import LocalAI, COMPLETION_MODEL, ASSISTANT_MODEL, rewrite_patch, presentation_check
from .languages import language_for,is_source,NAMES


class AIWorkbench:
    def open_brief(self):
        self.navigate(7)
        if not self.assistant_ready:self.ai_settings_toggle.setChecked(True)

    def build_ai(self):
        self.local_ai=LocalAI(); self.ai_worker=None; self.ai_ready=False; self.assistant_ready=False
        self.pending_ai_completion=False; self.ai_job_kind=None
        page=QWidget(); outer=QHBoxLayout(page); outer.setContentsMargins(16,16,16,16)
        content=QWidget(); content.setMaximumWidth(1000); outer.addStretch(); outer.addWidget(content,1); outer.addStretch()
        layout=QVBoxLayout(content); layout.setContentsMargins(0,0,0,0); layout.setSpacing(14)
        top=QHBoxLayout()
        title=QLabel("A brief, with context."); title.setObjectName("lensTitle"); top.addWidget(title,1)
        self.ai_settings_toggle=QPushButton("Model settings"); self.ai_settings_toggle.setCheckable(True); top.addWidget(self.ai_settings_toggle); layout.addLayout(top)
        self.ai_context_label=QLabel("Focus a node in the Lens, or place the cursor inside a function."); self.ai_context_label.setObjectName("briefContext"); self.ai_context_label.setWordWrap(True); layout.addWidget(self.ai_context_label)
        self.ai_status=QLabel("Local model interpretation is kept separate from recorded dependency evidence.")
        self.ai_status.setWordWrap(True); self.ai_status.setObjectName("muted"); layout.addWidget(self.ai_status)
        self.ai_settings=QFrame(); self.ai_settings.setObjectName("modelSettings"); settings=QVBoxLayout(self.ai_settings)
        description=QLabel("Local models · 16 GB RAM / 4 GB GPU preset\n1.5B autocomplete · optional 3B briefs and rewrites · one model active at a time")
        description.setObjectName("muted"); settings.addWidget(description)
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
        self.ai_rewrite=QPushButton("Propose a reviewable improvement"); self.ai_rewrite.clicked.connect(self.suggest_rewrite); actions.addWidget(self.ai_rewrite)
        self.ai_cancel=QPushButton("Cancel"); self.ai_cancel.clicked.connect(self.cancel_ai); self.ai_cancel.hide(); actions.addWidget(self.ai_cancel)
        actions.addStretch(); layout.addLayout(actions)
        self.ai_answer=BriefView(); self.ai_answer.setPlaceholderText("Choose a function or an impact path. Its explanation will appear here as a focused brief, with proposals kept separate from facts."); layout.addWidget(self.ai_answer,1)
        self.pages.addWidget(page)

    def initialize_ai(self):
        import os
        if os.environ.get("CHANGELENS_TEST_NO_AI")=="1":return
        try:enabled=json.loads((app_dir()/"local-ai.json").read_text(encoding="utf-8")).get("enabled",False)
        except (OSError,ValueError):enabled=False
        if enabled:QTimer.singleShot(0,self.connect_ai)

    def start_ai(self,task,callback,message,kind="assistant"):
        if self.ai_worker:return
        if kind!="completion":self.ai_status.setText(message)
        self.ai_cancel.show()
        for button in (self.ai_connect,self.ai_download,self.assistant_download,self.ai_explain,self.ai_rewrite,self.ai_readiness):button.setEnabled(False)
        worker=Worker(task,self); self.ai_worker=worker; self.ai_job_kind=kind; result={};self.refresh_actions()
        worker.done.connect(lambda value:result.update(value=value)); worker.failed.connect(lambda error:result.update(error=error))
        def finished():
            self.ai_worker=None; worker.deleteLater(); self.ai_cancel.hide()
            for button in (self.ai_connect,self.ai_download,self.assistant_download,self.ai_explain,self.ai_rewrite,self.ai_readiness):button.setEnabled(True)
            if "error" in result:
                message=result['error']
                if kind=='rewrite' and 'did not propose a change' in message:
                    message='No new improvement returned. Change the focus or regenerate.';self.refactor_context.setText(message)
                self.ai_status.setText(message); self.status.setText(message[:140])
            else:
                try:callback(result.get("value"))
                except Exception as exc:self.ai_status.setText(str(exc))
            if self.pending_ai_completion and self.ai_worker is None:
                self.pending_ai_completion=False; QTimer.singleShot(0,self.request_ai_completion)
            self.refresh_actions()
        worker.finished.connect(finished); worker.start()

    def cancel_ai(self):
        self.pending_ai_completion=False
        if self.ai_worker:self.ai_worker.cancel.set(); self.ai_status.setText("Cancelling local model request…")

    def connect_ai(self):
        def prepare(cancel,progress):
            models=self.local_ai.models(cancel)
            if COMPLETION_MODEL in models:self.local_ai.warm_up(cancel)
            return models
        def ready(models):
            self.ai_ready=COMPLETION_MODEL in models; self.assistant_ready=ASSISTANT_MODEL in models
            for editor in self.documents:editor.ai_enabled=self.ai_ready
            (app_dir()/"local-ai.json").write_text(json.dumps({"enabled":True}),encoding="utf-8")
            self.ai_status.setText(f"Autocomplete: {'ready' if self.ai_ready else 'download needed'} · Assistant: {'ready' if self.assistant_ready else 'optional download needed'}. All inference stays on this computer.")
            self.ai_button.setText("Brief")
            if self.assistant_ready:self.ai_settings_toggle.setChecked(False)
        self.start_ai(prepare,ready,"Preparing local presentation models. The first load can take longer; editing remains available…")

    def download_ai(self,model):
        def downloaded(result):self.ai_status.setText("Model downloaded. Checking availability…"); self.connect_ai()
        self.start_ai(lambda cancel,progress:self.local_ai.request("/api/pull",{"model":model,"stream":False},cancel,timeout=900),downloaded,"Downloading "+model+". This requires internet once; the model stays on this computer.")

    def related_ai_context(self,symbol=None):
        if not self.snapshot or not symbol:return ""
        targets={edge["callee"] for edge in self.snapshot.edges if edge["caller"]==symbol.id}
        return "\n".join(self.snapshot.symbols[sid].source[:250] for sid in sorted(targets)[:3] if sid in self.snapshot.symbols)[:700]

    def ai_selection(self):
        editor=self.current_editor(); document=self.current_document()
        if not editor or not document or not is_source(document.path):raise ValueError("Open a supported source file first.")
        line=editor.textCursor().blockNumber()+1; relative=document.path.relative_to(Path(self.snapshot.root)).as_posix()
        try:symbols=parse_file(relative,editor.toPlainText())[0]
        except SyntaxError:symbols=[]
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
        context=self.related_ai_context(symbol)
        def completed(result):
            if self.current_editor() is editor and editor.toPlainText()==code and editor.textCursor().position()==position and editor.completion_epoch==epoch:
                shown=editor.offer_ghost(result["text"])
                if shown:self.status.setText("Local AI suggestion · Tab to accept · Escape to dismiss")
        language=language_for(document.path)
        self.start_ai(lambda cancel,progress:self.local_ai.complete(code,offset,context,cancel,language),completed,"Generating a local code completion…",kind="completion")

    def explain_code(self):
        if not self.assistant_ready:self.open_brief(); self.ai_status.setText("Prepare the optional brief model once, then reconnect."); return
        try:editor,document,symbol,code=self.ai_selection()
        except ValueError as exc:self.ai_status.setText(str(exc)); return
        if symbol is None and not editor.textCursor().hasSelection():
            self.navigate(6); self.status.setText("Choose a function in the Lens or select code to explain."); return
        self.ai_context_label.setText((symbol.qualname if symbol else "Selected code")+" / "+document.path.name)
        self.navigate(7)
        self.ai_answer.clear()
        def explained(answer):self.ai_answer.setPlainText(brief_markdown(answer)); self.ai_status.setText("Local explanation ready. This is model interpretation, not execution evidence.")
        context=self.related_ai_context(symbol)
        language=NAMES[language_for(document.path)]
        self.start_ai(lambda cancel,progress:self.local_ai.assist(code,"Explain only this focused code. Do not invent existing tests or claim execution results.",context,cancel=cancel,structured=True,language=language),explained,"Reading the focused code locally…")

    def explain_impact(self,sid):
        if not self.snapshot or sid not in self.snapshot.symbols:return
        self.select_symbol(sid)
        if not self.assistant_ready:self.open_brief(); return
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

    def suggest_rewrite(self):
        if not self.assistant_ready:self.open_brief(); self.ai_status.setText("Prepare the optional brief model once, then reconnect."); return
        if self.worker or not self.save_all():return
        try:editor,document,_,_=self.ai_selection()
        except ValueError as exc:self.ai_status.setText(str(exc)); return
        root=Path(self.snapshot.root); relative=document.path.relative_to(root).as_posix(); line=editor.textCursor().blockNumber()+1
        self.operation.setCurrentIndex(self.operation.findData('ai_rewrite'));self.new_name.setText('ai_suggestion')
        self.patch=None;self.patch_list.clear();self.diff_view.clear();self.update_result_state();self.navigate(4)
        self.refactor_context.setText('Preparing a local proposal… Review its diff and validation before applying.')
        def task(cancel,progress):
            snapshot=index_repository(root,cancel,progress)
            matches=[s for s in snapshot.symbols.values() if s.path==relative and s.start<=line<=s.end and s.kind in {"function","async_function"}]
            if not matches:raise ValueError("Place the cursor inside the function to improve.")
            symbol=min(matches,key=lambda s:s.end-s.start)
            language=NAMES[language_for(document.path)]
            answer=self.local_ai.assist(symbol.source,"Suggest a small readability improvement with unchanged behavior. Return exactly the supplied declaration fragment and a short explanation. Preserve its name, signature and modifiers. Surrounding exports or const keywords outside the supplied fragment remain in the file; do not add them. Do not add dependencies or extra declarations.",rewrite=True,cancel=cancel,language=language)
            return snapshot,rewrite_patch(snapshot,symbol,answer)
        def suggested(result):
            if not self.snapshot or result[0].root!=self.snapshot.root:raise ValueError("Workspace changed; the previous AI suggestion was discarded.")
            self.operation.setCurrentIndex(self.operation.findData("ai_rewrite")); self.new_name.setText("ai_suggestion")
            self.ai_answer.setPlainText(result[1]["explanation"]); self.previewed(result)
            self.ai_status.setText("Suggested diff ready. Syntax checked; tests not run. Review before applying.")
        self.start_ai(task,suggested,"Preparing a reviewable local-model suggestion…",kind='rewrite')
