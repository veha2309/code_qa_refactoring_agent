"""A small editor overlay for previewing and applying refactors in place."""
import keyword
from pathlib import Path
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QSyntaxHighlighter, QTextCursor
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout

from .core import index_repository
from .languages import language_for, structural_refactoring
from .refactoring import apply_reviewed_patch, linked_tests, preview_refactoring


class PreviewColors(QSyntaxHighlighter):
    def highlightBlock(self, line):
        color = {"+": "#a9d9ac", "-": "#efacac", "@": "#9eb8c8"}.get(line[:1])
        if color:
            self.setFormat(0, len(line.encode("utf-16-le")) // 2, QColor(color))


class RefactorPanel(QFrame):
    def __init__(self, window, editor, start, name, rename, symbol, *, end=None, operation="rename",
                 selected_name=False):
        super().__init__(editor.viewport())
        self.setObjectName("inlineRefactor")
        self.editor, self.anchor, self.symbol = editor, start, symbol
        self.end = end
        self.result = None
        self.working = False
        self.writing = False
        self.layout_box = QVBoxLayout(self)
        self.layout_box.setContentsMargins(10, 8, 10, 8)
        self.layout_box.setSpacing(6)
        header = QHBoxLayout()
        title = QLabel("Refactor  " + name)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setObjectName("sectionTitle")
        title.setWordWrap(True)
        header.addWidget(title, 1)
        close = QPushButton("×")
        close.setAccessibleName("Close refactor panel")
        close.clicked.connect(lambda: window.dismiss_inline_refactor())
        header.addWidget(close)
        self.layout_box.addLayout(header)
        self.extraction = QComboBox()
        if selected_name:
            self.extraction.addItem("Rename", "rename")
        self.extraction.addItem("Extract function", "extract_method")
        value_label = "Extract variable" if getattr(editor, "_syntax_language", "python") == "python" else "Extract constant"
        self.extraction.addItem(value_label, "extract_variable")
        self.extraction.setAccessibleName("Extraction operation")
        self.extraction.setVisible(end is not None)
        self.layout_box.addWidget(self.extraction)
        self.new_name = QLineEdit()
        self.new_name.setPlaceholderText("New name")
        self.new_name.setAccessibleName("New name")
        self.rename = QPushButton("Preview extraction" if end is not None else "Preview rename")
        self.rename.setEnabled(False)
        self.rename.clicked.connect(lambda: window.preview_inline_refactor(self, self.extraction.currentData()
                                                                           if end is not None else "rename"))
        self.new_name.textChanged.connect(self.name_changed)
        self.new_name.returnPressed.connect(lambda: self.rename.click())
        row = QHBoxLayout()
        row.addWidget(self.new_name, 1)
        row.addWidget(self.rename)
        self.layout_box.addLayout(row)
        self.new_name.setVisible(rename)
        self.rename.setVisible(rename)
        if end is not None:
            self.extraction.setCurrentIndex(self.extraction.findData(operation))
            self.extraction.currentIndexChanged.connect(self.operation_changed)
        if end is not None and operation != "rename":
            names = set(re.findall(r"[\w$]+", editor.toPlainText()))
            candidate, number = "extracted", 2
            while candidate in names:
                candidate = f"extracted{number}"
                number += 1
            self.new_name.setText(candidate)
        if operation == "rename":
            self.rename.setText("Preview rename")
        self.improve = QPushButton("Preview improvement" if not symbol else "Improve " + symbol.name)
        self.improve.clicked.connect(lambda: window.preview_inline_refactor(self, "ai_rewrite"))
        self.improve.setVisible(symbol is not None)
        self.layout_box.addWidget(self.improve)
        self.status = QLabel("Choose an action to see the proposed edit.")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setObjectName("muted")
        self.layout_box.addWidget(self.status)
        self.save_file = QPushButton("Save file and keep selection")
        self.save_file.setVisible(editor.document().isModified())
        self.save_file.clicked.connect(lambda: window.save_inline_source(self))
        self.layout_box.addWidget(self.save_file)
        if editor.document().isModified():
            self.status.setText("Save this file to preview the refactor.")
        self.files = QComboBox()
        self.files.setAccessibleName("Files in preview")
        self.files.currentIndexChanged.connect(self.show_file)
        self.files.hide()
        self.layout_box.addWidget(self.files)
        self.diff = QPlainTextEdit()
        self.diff.setReadOnly(True)
        self.diff.setAccessibleName("Proposed changes")
        self.diff.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.diff.setFixedHeight(146)
        self.diff_colors = PreviewColors(self.diff.document())
        self.diff.hide()
        self.layout_box.addWidget(self.diff)
        self.apply = QPushButton("Apply refactor")
        self.apply.setObjectName("lensAction")
        self.apply.clicked.connect(lambda: window.apply_inline_refactor(self))
        self.apply.hide()
        self.layout_box.addWidget(self.apply)
        self.undo = QPushButton("Undo refactor")
        self.undo.clicked.connect(lambda: window.undo_inline_refactor(self))
        self.undo.hide()
        self.layout_box.addWidget(self.undo)
        escape = QShortcut(QKeySequence("Escape"), self)
        escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escape.activated.connect(window.dismiss_inline_refactor)

    def name_changed(self, value):
        self.rename.setEnabled(bool(value.strip()) and not self.working)
        if self.result:
            self.clear_preview()
            self.status.setText("Preview this change before applying.")
            self.place()

    def operation_changed(self):
        self.rename.setText("Preview rename" if self.extraction.currentData() == "rename" else "Preview extraction")
        self.name_changed(self.new_name.text())

    def clear_preview(self):
        self.result = None
        self.files.hide()
        self.diff.hide()
        self.apply.hide()

    def show_file(self, index):
        if self.result and index >= 0:
            lines = self.result[1]["files"][index]["diff"].splitlines()
            self.diff.setPlainText("\n".join(lines[2:]))

    def place(self):
        viewport = self.parentWidget()
        width = min(600 if self.result else 330, viewport.width() - 12)
        self.setFixedWidth(max(1, width))
        self.layout_box.activate()
        self.setFixedHeight(self.layout_box.totalSizeHint().height())
        cursor = QTextCursor(self.editor.document())
        cursor.setPosition(min(self.end if self.end is not None else self.anchor,
                               self.editor.document().characterCount() - 1))
        rect = self.editor.cursorRect(cursor)
        x = max(6, min(rect.left(), viewport.width() - self.width() - 6))
        below = rect.bottom() + 6
        y = below if below + self.height() <= viewport.height() - 6 else rect.top() - self.height() - 6
        self.move(x, max(6, y))
        self.raise_()

    def show_status(self, message, *, working=False):
        self.working = working
        self.new_name.setEnabled(not working)
        self.rename.setEnabled(not working and bool(self.new_name.text().strip()))
        self.improve.setEnabled(not working)
        self.extraction.setEnabled(not working)
        self.apply.setEnabled(not working)
        self.undo.setEnabled(not working)
        self.status.setText(message)
        self.place()

    def show_preview(self, result):
        self.result = result
        patch = result[1]
        self.files.blockSignals(True)
        self.files.clear()
        self.files.addItems([row["path"] for row in patch["files"]])
        self.files.blockSignals(False)
        self.show_file(0)
        self.files.setVisible(len(patch["files"]) > 1)
        self.diff.show()
        self.apply.show()
        count = len(patch["files"])
        self.show_status(f"{count} file{'s' if count != 1 else ''} in this preview. Tests have not run.")


class InlineRefactorWorkbench:
    inline_refactor = None

    def open_inline_refactor(self, editor, start, end):
        document = self.documents.get(editor)
        if not document or editor is not self.current_editor() or self.pages.currentIndex() != 0:
            return
        language = language_for(document.path)
        if not language or editor.isReadOnly():
            return
        cursor = QTextCursor(editor.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        name = cursor.selectedText()
        path = document.path.relative_to(self.snapshot.root).as_posix()
        line = cursor.blockNumber() + 1
        functions = [symbol for symbol in self._cursor_file_symbols
                     if symbol.path == path and symbol.kind in {"function", "async_function"}
                     and symbol.start <= line <= symbol.end]
        symbol = min(functions, key=lambda item: (item.name != name, item.end - item.start), default=None)
        structural = structural_refactoring(document.path)
        if not structural and not symbol:
            return
        self.dismiss_inline_refactor()
        editor.completion_timer.stop()
        editor.ai_timer.stop()
        editor.completer.popup().hide()
        panel = RefactorPanel(self, editor, start, name, structural, symbol)
        self.inline_refactor = panel
        panel.place()
        panel.show()

    def open_inline_extraction(self, editor, start, end, operation=None):
        document = self.documents.get(editor)
        if not document or editor is not self.current_editor() or self.pages.currentIndex() != 0:
            return
        if editor.isReadOnly() or not structural_refactoring(document.path):
            return
        cursor = QTextCursor(editor.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        text = cursor.selectedText()
        selected_name = bool(re.fullmatch(r"(?:[^\W\d]|\$)[\w$]*", text) and not keyword.iskeyword(text))
        self.dismiss_inline_refactor()
        panel = RefactorPanel(self, editor, start, text if selected_name else "selection", True, None,
                              end=end, operation=operation or ("rename" if selected_name else "extract_method"),
                              selected_name=selected_name)
        self.inline_refactor = panel
        panel.place()
        panel.show()

    def save_inline_source(self, panel):
        if self.inline_refactor is panel and not self.worker and self.save_editor(panel.editor):
            panel.save_file.hide()
            panel.show_status("File saved. Preview the refactor when you're ready.")

    def editor_refactor_action(self, editor, operation):
        cursor = editor.textCursor()
        if operation != "rename":
            if not cursor.hasSelection():
                self.notify("Select the code you want to extract in the editor.")
                return
            self.open_inline_extraction(editor, cursor.selectionStart(), cursor.selectionEnd(), operation)
        else:
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
            if cursor.hasSelection():
                self.open_inline_refactor(editor, cursor.selectionStart(), cursor.selectionEnd())

    def dismiss_inline_refactor(self, editor=None, *, source_changed=False):
        panel = self.inline_refactor
        if not panel or (editor is not None and panel.editor is not editor):
            return
        if source_changed and panel.writing:
            return
        self.inline_refactor = None
        panel.hide()
        panel.deleteLater()

    def preview_inline_refactor(self, panel, operation):
        if self.inline_refactor is not panel or panel.working:
            return
        if self.worker or self.ai_worker and operation == "ai_rewrite":
            panel.show_status("Another operation is running. Try again when it finishes.")
            return
        if any(editor.document().isModified() for editor in self.documents):
            panel.show_status("Save your editor changes before previewing the refactor.")
            return
        self.check_timer.stop()
        self.pending_check = False
        document = self.documents[panel.editor]
        root = Path(self.snapshot.root)
        path = document.path.relative_to(root).as_posix()
        digest = document.digest
        offset = panel.editor.code_offset(panel.anchor)
        end = panel.editor.code_offset(panel.end) if panel.end is not None else None
        name = panel.new_name.text().strip()
        selected = panel.symbol
        panel.clear_preview()
        panel.undo.hide()
        panel.show_status("Preparing preview…", working=True)

        def task(cancel, progress):
            snapshot = index_repository(root, cancel, progress)
            if snapshot.hashes.get(path) != digest:
                raise ValueError("This file changed on disk. Refresh it and click the name again.")
            if operation != "ai_rewrite":
                patch = preview_refactoring(snapshot, path, operation, name, offset, end, cancel=cancel, progress=progress)
                line = document.text.count("\n", 0, offset) + 1
                focus = selected or min((symbol for symbol in snapshot.symbols.values()
                                         if symbol.path == path and symbol.start <= line <= symbol.end),
                                        key=lambda symbol:(symbol.end-symbol.start,symbol.kind=="module"),default=None)
                if focus and focus.id in snapshot.symbols:
                    patch["linked_tests"] = linked_tests(snapshot, [focus.id], cancel)
            else:
                from .ai_workbench import build_rewrite_proposal
                symbol = snapshot.symbols.get(selected.id)
                if not symbol:
                    raise ValueError("The function changed. Click it again to preview an improvement.")
                patch = build_rewrite_proposal(self.local_ai, snapshot, symbol, "", 0, cancel)
            return snapshot, patch

        def ready(result):
            if self.inline_refactor is panel:
                panel.show_preview(result)
                self.notify("Refactor preview is ready in the editor.")

        def failed(message):
            if self.inline_refactor is panel:
                panel.show_status(message)

        if operation != "ai_rewrite":
            self.start(task, ready, on_error=failed)
        else:
            self.start_ai(task, ready, "Preparing an inline improvement…", kind="inline_rewrite", on_error=failed)

    def apply_inline_refactor(self, panel):
        if self.inline_refactor is not panel or not panel.result or self.worker:
            return
        if any(editor.document().isModified() for editor in self.documents):
            panel.show_status("Save your changes and preview the refactor again.")
            return
        snapshot, patch = panel.result
        panel.writing = True
        panel.show_status("Applying refactor…", working=True)

        def applied(receipt):
            self.applied_patch = receipt
            if self.inline_refactor is panel:
                panel.clear_preview()
                panel.new_name.hide()
                panel.rename.hide()
                panel.improve.hide()
                panel.extraction.hide()
            self.invalidate_results()
            self.refresh_saved_review(navigate_to_review=False, after_review=ready, on_error=refresh_failed)

        def ready():
            if self.inline_refactor is panel:
                panel.writing = False
                panel.undo.show()
                panel.show_status("Refactor applied.")

        def failed(message):
            if self.inline_refactor is panel:
                panel.writing = False
                panel.show_status(message)

        def refresh_failed(message):
            if self.inline_refactor is panel:
                panel.undo.show()
                failed("Refactor applied. Refresh the editor to see the saved code. " + message)

        self.start_patch_write(lambda: apply_reviewed_patch(snapshot, patch), applied, on_error=failed)

    def undo_inline_refactor(self, panel):
        if self.inline_refactor is not panel or self.worker:
            return
        self.dismiss_inline_refactor()
        self.undo_patch(stay_here=True)
