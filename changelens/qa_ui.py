"""The workbench entry point for evidence, linked tests and reviewed refactors."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QHeaderView, QPlainTextEdit, QTreeWidget, QTreeWidgetItem

from .core import ensure_fresh
from .languages import NAMES, language_for
from .qa_review import model_findings, source_evidence
from .workspace import analyze_workspace


REVIEW_PAGE = 9
VISIBLE_FINDINGS = 250


class QAWorkbench:
    def build_qa_review(self):
        from .workbench import action, column, text

        page, layout = column()
        heading = QHBoxLayout()
        heading.addWidget(text("Review saved code", "lensTitle"), 1)
        self.qa_changes = action("Review changes", self.review_saved, True)
        self.qa_focus = action("Review function", lambda: self.review_saved("function"))
        self.qa_file = action("Review file", lambda: self.review_saved("file"))
        self.qa_symbol = action("Choose function…", self.choose_qa_symbol)
        for button in (self.qa_changes, self.qa_focus, self.qa_file, self.qa_symbol):
            heading.addWidget(button)
        layout.addLayout(heading)
        self.qa_scope = text("Open a folder or try a sample to begin.", "muted")
        self.qa_scope.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.qa_scope)
        row = QHBoxLayout()
        self.qa_model = action("Look for possible bugs", self.review_with_model)
        self.qa_cancel = action("Cancel model review", self.cancel_ai)
        self.qa_diff = action("Saved diffs…", lambda: self.open_tool_window(1, "Saved changes"))
        self.qa_tests = action("Linked tests…", lambda: self.open_tool_window(3, "Linked tests"))
        for button in (self.qa_model, self.qa_cancel, self.qa_diff, self.qa_tests):
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        self.qa_model_status = text("Optional local Ollama review", "muted")
        self.qa_model_status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.qa_model_status)
        self.qa_items = QTreeWidget()
        self.qa_items.setRootIsDecorated(False)
        self.qa_items.setHeaderLabels(["Type", "What to look at", "Where"])
        self.qa_items.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.qa_items.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.qa_items.currentItemChanged.connect(self.qa_selection_changed)
        self.qa_items.itemActivated.connect(lambda *_: self.open_qa_evidence())
        layout.addWidget(self.qa_items, 1)
        self.qa_detail = QPlainTextEdit()
        self.qa_detail.setObjectName("qaFindingBody")
        self.qa_detail.setReadOnly(True)
        self.qa_detail.setMinimumHeight(160)
        layout.addWidget(self.qa_detail, 2)
        self.qa_show_evidence = QCheckBox("Show source quotes")
        self.qa_show_evidence.toggled.connect(self.qa_selection_changed)
        layout.addWidget(self.qa_show_evidence)
        row = QHBoxLayout()
        self.qa_source = action("Open code", self.open_qa_evidence)
        self.qa_fix = action("Preview fix", self.preview_qa_fix, True)
        self.qa_refactor = action("Refactor focused code", self.refactor_qa_evidence)
        self.qa_undo = action("Undo applied patch", self.undo_patch)
        for button in (self.qa_source, self.qa_fix, self.qa_refactor, self.qa_undo):
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        self.pages.addWidget(page)

    def review_saved(self, scope=None):
        if not self.snapshot or self.worker:
            return
        focus = None
        if scope:
            document, editor = self.current_document(), self.current_editor()
            if not document or not language_for(document.path):
                self.notify("Open a supported source file to review its saved code.", True)
                return
            if editor.document().isModified():
                self.notify("Save the focused file so the review uses the current source positions.", True)
                return
            focus = {"review": True, "path": document.path.relative_to(self.snapshot.root).as_posix(),
                     "line": editor.textCursor().blockNumber() + 1 if scope == "function" else None}
        self.refresh_saved_review(focus)

    def refresh_saved_review(self, focus=None, *, after_review=None, navigate_to_review=True, on_error=None):
        self.check_timer.stop()
        self.preview_timer.stop()
        self.pending_check = False
        root, mode, model = Path(self.snapshot.root), self.comparison.currentData(), self.model_path()
        if navigate_to_review:
            self.navigate(REVIEW_PAGE)
        self.qa_scope.setText("Checking saved source…")
        def task(cancel, progress):
            result = analyze_workspace(root, focus, mode, model, cancel, progress)
            ensure_fresh(result[0])
            return result
        def ready(result):
            self.analyzed(result, False)
            if after_review:
                after_review()
        self.start(task, ready, on_error=on_error)

    def choose_qa_symbol(self):
        def select(symbol):
            self.open_file(symbol.path, symbol.start)
            if self.editors.get(symbol.path) is self.current_editor():
                self.review_saved("function")
        self.choose_workspace_function("Review a saved function…", select)

    def populate_qa_review(self):
        if not hasattr(self, "qa_items"):
            return
        self.qa_items.clear()
        self.qa_model_status.setText("Optional local Ollama review")
        if self.report:
            for row in self.report.get("qa_items", [])[:VISIBLE_FINDINGS]:
                self.add_qa_item(row)
            self.qa_items.setCurrentItem(self.qa_items.topLevelItem(0))
        self.update_qa_actions()

    def add_qa_item(self, row):
        label = {"Model interpretation": "Possible bug", "Impact evidence": "Check impact",
                 "Parser error": "Read error", "Analysis gap": "Test gap" if row.get("sid") else "Review limit"}
        item = QTreeWidgetItem([label[row["kind"]], row["title"], f"{row['path']}:{row['line']}"])
        item.setData(0, Qt.ItemDataRole.UserRole, row)
        if row["kind"] == "Model interpretation":
            index = sum(self.qa_items.topLevelItem(i).text(0) == "Possible bug"
                        for i in range(self.qa_items.topLevelItemCount()))
            self.qa_items.insertTopLevelItem(index, item)
        else:
            self.qa_items.addTopLevelItem(item)
        return item

    def qa_selection(self):
        item = self.qa_items.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item else None

    def qa_selection_changed(self, *_):
        row = self.qa_selection()
        if row:
            source = f"{row['path']}:{row['line']}"
            if row.get("end") and row["end"] != row["line"]:
                source += f"–{row['end']}"
            if row.get("historical"):
                source += " · previous version"
            details = [row["title"] + " · " + source]
            if row.get("evidence_id"):
                action = "Preview a fix or open the code. " if self.qa_fix_symbol(row) else "Open the code or saved diff to investigate. "
                details.extend(["Why it matters\n" + row["detail"],
                                "What to do\n" + action + row["next"]])
                if self.qa_show_evidence.isChecked():
                    label = "Previous code" if row.get("historical") else "Current code"
                    details.extend([label + "\n" + row["witness"], "Expected behavior comes from\n" + row["basis"],
                                    "Source excerpt\n" + row["excerpt"]])
            else:
                details.extend(["What we saw\n" + row["detail"], "Why it matters\n" + row["why"],
                                "What to do\n" + row["next"]])
            self.qa_detail.setPlainText("\n\n".join(details))
        else:
            self.qa_detail.clear()
        self.update_qa_actions()

    def update_qa_actions(self):
        if not hasattr(self, "qa_items"):
            return
        opened, busy = bool(self.snapshot), bool(self.worker)
        fresh = bool(self.report and not self.report_stale and self.report["snapshot"] == self.snapshot.id)
        model_busy = self.ai_job_kind == "qa_review"
        focus = bool(self.current_document() and language_for(self.current_document().path))
        row = self.qa_selection()
        self.qa_changes.setEnabled(opened and not busy)
        self.qa_focus.setEnabled(opened and focus and not busy)
        self.qa_file.setEnabled(opened and focus and not busy)
        self.qa_symbol.setEnabled(opened and not busy)
        self.qa_model.setEnabled(fresh and not busy and not self.ai_worker and bool(
            self.report.get("review_focus") or self.report["changes"]["files"]))
        self.qa_cancel.setVisible(model_busy)
        self.qa_diff.setEnabled(bool(self.report and self.report["changes"]["files"]))
        self.qa_tests.setEnabled(bool(self.report and self.report["tests"]))
        self.qa_source.setEnabled(bool(row and self.report))
        self.qa_source.setText("Open saved diff" if row and row.get("historical") else "Open code")
        possible_bug = bool(row and row.get("evidence_id"))
        self.qa_show_evidence.setVisible(possible_bug)
        self.qa_fix.setVisible(possible_bug)
        fix_symbol = self.qa_fix_symbol(row) if fresh and possible_bug else None
        self.qa_fix.setEnabled(bool(fix_symbol and not busy and not self.ai_worker))
        self.qa_fix.setToolTip("Prepare an edit you can inspect before applying." if fix_symbol
                               else "Open the code to edit this item. A fix preview needs a current finding inside a function.")
        target = not row.get("historical") and bool(language_for(row["path"])) if row else focus
        self.qa_refactor.setEnabled(fresh and not busy and target)
        self.qa_refactor.setVisible(not possible_bug)
        receipt = getattr(self, "applied_patch", None)
        self.qa_undo.setEnabled(bool(opened and receipt and receipt["root"] == self.snapshot.root and not busy))
        if not self.report:
            self.qa_scope.setText("Checking saved source…" if busy else "Open a folder or try a sample to begin.")
            return
        summary = self.report["summary"]
        scope = self.report.get("review_focus")
        if scope:
            comparison = "Focused source · " + scope["path"]
        else:
            comparison = self.report["comparison_context"].get("label", "Saved comparison")
            if not self.report["changes"]["files"]:
                comparison += " · No saved changes. Review a function or file to begin."
        status = f"{comparison}\n{summary['recommended_tests']} linked tests"
        structural = [NAMES[name] for name in self.snapshot.profile["languages"]
                      if name in {"java", "csharp", "go", "rust"}]
        if structural:
            status += " · Structural evidence and test recommendations for " + ", ".join(structural)
        result = self.report.get("test_run") or self.report.get("demo_validation", {}).get("selected")
        status += f" · Tests {result['status']}" if result else " · Tests not run for this review"
        if receipt and receipt["root"] == self.snapshot.root and receipt.get("finding_title"):
            status += f"\nFix applied for “{receipt['finding_title']}”"
            if not result:
                status += ". Run the linked tests to check it."
        if self.report_stale:
            status += "\nSaved-source results need a refresh. Unsaved editor changes are kept in the editor."
        if len(self.report.get("qa_items", [])) > VISIBLE_FINDINGS:
            status += f"\nShowing the first {VISIBLE_FINDINGS} static items. Choose a file or function to narrow the review."
        self.qa_scope.setText(status)

    def qa_fix_symbol(self, row):
        if row.get("historical"):
            return None
        candidates = (symbol for symbol in self.snapshot.symbols.values()
                      if symbol.path == row["path"] and symbol.kind in {"function", "async_function"}
                      and symbol.start <= row["line"] <= symbol.end
                      and row["witness"] in symbol.source)
        return min(candidates, key=lambda symbol: symbol.end - symbol.start, default=None)

    def preview_qa_fix(self):
        if not self.qa_fix.isEnabled():
            return
        row = self.qa_selection()
        symbol = self.qa_fix_symbol(row)
        self.open_file(symbol.path, row["line"])
        if self.current_editor() is not None and self.current_editor() is self.editors.get(symbol.path):
            self.suggest_rewrite(fix={"snapshot": self.snapshot.id, "symbol": symbol.id, "finding": row})

    def open_qa_evidence(self):
        row = self.qa_selection()
        if not row:
            return
        if row.get("historical"):
            for index, change in enumerate(self.change_rows):
                if change["path"] == row["path"]:
                    self.change_list.setCurrentRow(index)
                    self.open_tool_window(1, "Saved changes")
                    before = self.changes_view.before
                    if row["line"] in before.line_numbers:
                        before.goto_line(before.line_numbers.index(row["line"]) + 1)
                    return
        else:
            self.open_file(row["path"], row["line"])
            self.navigate(0)

    def refactor_qa_evidence(self):
        if not self.qa_refactor.isEnabled():
            return
        row = self.qa_selection()
        if row and not row.get("historical"):
            path, line = row["path"], row["line"]
            candidates = [symbol for symbol in self.snapshot.symbols.values()
                          if symbol.path == path and symbol.kind in {"function", "async_function"}
                          and symbol.start <= row.get("end", line) and symbol.end >= line]
            if candidates:
                line = min(candidates, key=lambda symbol: (max(0, symbol.start - line),
                                                           symbol.end - symbol.start)).start
            self.open_file(path, line)
            if not self.editors.get(path) or self.current_editor() is not self.editors[path]:
                return
        self.patch = None
        self.patch_list.clear()
        self.diff_view.clear()
        self.update_result_state()
        self.update_refactor_context()
        self.open_tool_window(4, "Refactor focused code")

    def review_with_model(self):
        if not self.qa_model.isEnabled():
            return
        snapshot, report = self.snapshot, self.report
        client = self.local_ai
        for index in reversed(range(self.qa_items.topLevelItemCount())):
            item = self.qa_items.topLevelItem(index)
            if item.data(0, Qt.ItemDataRole.UserRole)["kind"] == "Model interpretation":
                self.qa_items.takeTopLevelItem(index)
        self.qa_model_status.setText("Reviewing bounded saved source with local Ollama…")

        def task(cancel, progress):
            ensure_fresh(snapshot)
            entries, limited = source_evidence(snapshot, report, report.get("review_focus"), cancel)
            if not entries:
                raise ValueError("No source excerpt fits this scope. Review a smaller function.")
            rows, sent, unsupported = model_findings(client, entries, cancel)
            ensure_fresh(snapshot)
            return rows, sent, limited or len(sent) != len(entries), unsupported

        def ready(result):
            if self.report is not report or self.report_stale or self.snapshot.id != snapshot.id:
                self.qa_model_status.setText("Source changed during model review. Refresh and try again.")
                return
            rows, sent, limited, unsupported = result
            first = None
            for row in rows:
                item = self.add_qa_item(row)
                if first is None:
                    first = item
            if first:
                self.qa_items.setCurrentItem(first)
            reviewed = ", ".join(f"{entry['path']}:{entry['line']}–{entry['end']} ({entry['side']})" for entry in sent)
            outcome = ("1 possible bug" if len(rows) == 1 else f"{len(rows)} possible bugs") if rows else "The model returned no findings"
            if unsupported:
                if not rows:
                    outcome = "No findings supported by the quoted evidence"
                outcome += f" · {unsupported} discarded for insufficient source support"
            self.qa_model_status.setText(
                f"{outcome} · {reviewed}" + (" · Context limited to these excerpts" if limited else ""))

        self.start_ai(task, ready, "Reviewing bounded source locally…", kind="qa_review",
                      on_error=self.qa_model_status.setText)
