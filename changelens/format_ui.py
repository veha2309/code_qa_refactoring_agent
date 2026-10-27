"""Review formatting and apply to a live buffer as one undoable operation."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QDialog,QHBoxLayout,QLabel,QPushButton,QVBoxLayout
from pathlib import Path
from .widgets import DiffViewer


def apply_to_editor(editor,result):
    if editor.isReadOnly():raise ValueError('This document is read-only.')
    if editor.toPlainText()!=result['before']:raise ValueError('The document changed after this preview. Format it again to review a fresh diff.')
    position=editor.textCursor().position();scroll=editor.verticalScrollBar().value()
    editor.clear_ghost();editor.completion_timer.stop();editor.ai_timer.stop()
    cursor=QTextCursor(editor.document());cursor.beginEditBlock();cursor.select(QTextCursor.SelectionType.Document);cursor.insertText(result['after']);cursor.endEditBlock()
    cursor.setPosition(min(position,editor.document().characterCount()-1));editor.setTextCursor(cursor)
    editor.verticalScrollBar().setValue(scroll)


class FormatPreview(QDialog):
    def __init__(self,result,apply,parent=None):
        super().__init__(parent);self.setObjectName('formatPreview');self.setWindowTitle('Format document — '+result['engine']);self.resize(1160,740)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        layout=QVBoxLayout(self);layout.setContentsMargins(24,22,24,20);layout.setSpacing(14)
        heading=QLabel('Review formatting');heading.setObjectName('lensTitle');layout.addWidget(heading)
        context=QLabel(result['engine']+' · '+Path(result['path']).name);context.setToolTip(result['path']);context.setObjectName('muted');context.setWordWrap(True);layout.addWidget(context)
        self.diff=DiffViewer();self.diff.set_versions(result['before'],result['after'],Path(result['path']).name);layout.addWidget(self.diff,1)
        note=QLabel(result['note']+' Applying changes only the editor; Ctrl+S saves.');note.setWordWrap(True);note.setObjectName('muted');layout.addWidget(note)
        row=QHBoxLayout();self.error=QLabel();self.error.setWordWrap(True);row.addWidget(self.error,1)
        cancel=QPushButton('Keep original');cancel.clicked.connect(self.reject);row.addWidget(cancel)
        self.apply_button=QPushButton('Apply to editor');self.apply_button.setObjectName('lensAction');row.addWidget(self.apply_button)
        def accepted():
            try:apply()
            except (ValueError,RuntimeError) as exc:self.error.setText(str(exc));self.apply_button.setEnabled(False);return
            self.accept()
        self.apply_button.clicked.connect(accepted);layout.addLayout(row)
