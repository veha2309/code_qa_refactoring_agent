"""Visible edit hunks, undoable buffer reverts and saved-version previews."""
import difflib
from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QComboBox,QListWidget,QListWidgetItem,QPushButton,QLabel,QSplitter,QMessageBox
from .widgets import DiffViewer
from .core import decode_source
from .change_history import versions,restore


def hunks(before,after):
    a,b=before.splitlines(True),after.splitlines(True)
    return [{'tag':tag,'old_start':i,'old_end':j,'new_start':k,'new_end':l,'before':''.join(a[i:j]),'after':''.join(b[k:l])} for tag,i,j,k,l in difflib.SequenceMatcher(None,a,b,autojunk=True).get_opcodes() if tag!='equal']


def replace_buffer(editor,text):
    cursor=editor.textCursor();position=cursor.position();cursor.beginEditBlock();cursor.select(QTextCursor.SelectionType.Document);cursor.insertText(text);cursor.endEditBlock();cursor.setPosition(min(position,editor.document().characterCount()-1));editor.setTextCursor(cursor)


class EditReview(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.editor=window.current_editor();self.document=window.current_document();self.setWindowTitle('Review and revert · '+self.document.path.name);self.resize(1150,750)
        col=QVBoxLayout(self);row=QHBoxLayout();self.mode=QComboBox();self.mode.addItems(['Unsaved edits','Since this tab opened','Saved file history','Project comparison']);self.mode.setCurrentIndex(3);self.mode.currentIndexChanged.connect(self.refresh);row.addWidget(self.mode,1)
        refresh=QPushButton('Refresh');refresh.clicked.connect(self.refresh);row.addWidget(refresh);col.addLayout(row)
        self.note=QLabel();self.note.setWordWrap(True);col.addWidget(self.note)
        split=QSplitter();self.rows=QListWidget();self.rows.setMaximumWidth(290);self.rows.currentRowChanged.connect(self.select);split.addWidget(self.rows);self.diff=DiffViewer();split.addWidget(self.diff);col.addWidget(split,1)
        actions=QHBoxLayout();self.one=QPushButton('Revert selected hunk');self.one.clicked.connect(self.revert_one);actions.addWidget(self.one)
        self.all=QPushButton('Revert all shown edits');self.all.clicked.connect(self.revert_all);actions.addWidget(self.all)
        self.restore_button=QPushButton('Restore version before this save');self.restore_button.clicked.connect(self.restore_version);actions.addWidget(self.restore_button);col.addLayout(actions);self.refresh()

    def valid_editor(self):
        return self.editor in self.window.documents

    def refresh(self,*args):
        if not self.valid_editor():
            self.note.setText('This file was closed or the project changed. Reopen it to review edits.');self.one.setEnabled(False);self.all.setEnabled(False);self.restore_button.setEnabled(False);return
        self.rows.blockSignals(True);self.rows.clear();self.snapshot=self.editor.toPlainText();self.digest=self.document.digest;history=self.mode.currentIndex()==2
        self.entries=[]
        if history:
            try:self.entries=versions(self.document.path)
            except Exception as exc:self.note.setText(str(exc))
            for record in self.entries:
                self.rows.addItem(datetime.fromtimestamp(record['created']).strftime('%d %b %H:%M:%S')+' · '+record['origin'])
            self.note.setText('Restore previews the selected before-save version against the current file. Saved history retains 30 changes per file. A restore is also recorded. Save or discard unsaved edits first.')
        else:
            self.base=self.document.text if self.mode.currentIndex()==0 else self.editor.change_base_text if self.mode.currentIndex()==3 else self.editor.opening_text
            self.entries=hunks(self.base,self.snapshot)
            for h in self.entries:self.rows.addItem(f"{h['tag']} · current lines {h['new_start']+1}–{max(h['new_start']+1,h['new_end'])}")
            self.note.setText(f"{len(self.entries)} changed hunks. Reverts change the buffer as one undo step; Ctrl+S writes the file. Comparison: "+('last save' if self.mode.currentIndex()==0 else self.editor.change_base_label if self.mode.currentIndex()==3 else 'tab opening state (including subsequent saves)'))
        self.rows.blockSignals(False);self.one.setVisible(not history);self.all.setVisible(not history);self.restore_button.setVisible(history)
        self.all.setEnabled(bool(self.entries) and not self.editor.isReadOnly());self.one.setEnabled(self.all.isEnabled());self.restore_button.setEnabled(bool(self.entries) and not self.editor.document().isModified() and not self.editor.isReadOnly())
        if self.entries:
            line=self.editor.textCursor().blockNumber();index=next((i for i,h in enumerate(self.entries) if not history and h['new_start']<=line<max(h['new_start']+1,h['new_end'])),0)
            self.rows.setCurrentRow(index)
        else:self.diff.clear();self.note.setText(self.note.text()+' · No changes in this view.')

    def select(self,index):
        if not 0<=index<len(self.entries):return
        if self.mode.currentIndex()==2:
            row=self.entries[index];before=decode_source(row['before'],self.document.path).replace('\r\n','\n');self.diff.set_versions(before,self.document.text,self.document.path.name+' · selected before-save version → current saved file')
        else:
            h=self.entries[index];self.diff.set_versions(h['before'],h['after'],f"{self.document.path.name} · current line {h['new_start']+1}")
            self.editor.goto_line(h['new_start']+1)

    def check(self):
        if not self.valid_editor() or self.editor.toPlainText()!=self.snapshot:
            self.note.setText('Editor changed or switched since preview. Refresh before reverting.');return False
        return not self.editor.isReadOnly()

    def revert_one(self):
        index=self.rows.currentRow()
        if not self.check() or not 0<=index<len(self.entries):return
        h=self.entries[index];lines=self.snapshot.splitlines(True)
        replace_buffer(self.editor,''.join(lines[:h['new_start']])+h['before']+''.join(lines[h['new_end']:]))
        self.refresh()

    def revert_all(self):
        if self.check():replace_buffer(self.editor,self.base);self.refresh()

    def restore_version(self):
        index=self.rows.currentRow()
        if not self.check() or not 0<=index<len(self.entries) or self.editor.document().isModified():return
        try:
            fresh=restore(self.document.path,self.entries[index]['id'],self.digest)
            self.window.documents[self.editor]=self.document=fresh
            replace_buffer(self.editor,fresh.text);self.editor.document().setModified(False)
            self.window.files_changed(str(fresh.path));self.window.notify('Saved version restored. History contains a recovery point for this restore.');self.refresh()
        except (OSError,ValueError) as exc:self.note.setText(str(exc))
