"""Visible counts, highlights and project search results."""
from PySide6.QtCore import Qt,QTimer,QEvent
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QWidget,QHBoxLayout,QVBoxLayout,QLineEdit,QLabel,QPushButton,QCheckBox,QDialog,QTreeWidget,QTreeWidgetItem,QHeaderView
from .search import text_matches,search_project
from .jobs import Worker

class FindBar(QWidget):
    def __init__(self,editor,project,parent=None):
        super().__init__(parent);self.editor=editor;self.matches=[];self.index=-1;self.limit=False;self._bound=None
        row=QHBoxLayout(self);row.setContentsMargins(8,6,8,6);row.setSpacing(8)
        self.query=QLineEdit();self.query.setPlaceholderText('Find in this file…');row.addWidget(self.query,1)
        self.case=QCheckBox('Aa');self.case.setToolTip('Match case');row.addWidget(self.case)
        self.count=QLabel('Type to find');self.count.setMinimumWidth(170);row.addWidget(self.count)
        for label,callback in [('↑',lambda:self.step(-1)),('↓',lambda:self.step(1)),('Search project',lambda:project(self.query.text())),('Close',self.dismiss)]:
            button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(120);self.timer.timeout.connect(self.refresh)
        self._move=True;self.query.installEventFilter(self)
        self.query.textChanged.connect(lambda:self.queue(True));self.case.toggled.connect(lambda:self.queue(True))
        self.query.returnPressed.connect(lambda:self.step(1));self.hide()

    def open(self):
        self.show();self.bind();self.query.setFocus();self.query.selectAll();self.refresh()

    def bind(self):
        editor=self.editor()
        if self._bound is editor:return
        if self._bound is not None:
            try:self._bound.textChanged.disconnect(self.queue_refresh);self._bound.search_ranges=[];self._bound.highlight_lines()
            except (RuntimeError,TypeError):pass
        self._bound=editor
        if editor:editor.textChanged.connect(self.queue_refresh)

    def queue_refresh(self):
        if self.isVisible():self.queue(False)

    def queue(self,move):self._move=move;self.timer.start()

    def eventFilter(self,watched,event):
        if event.type()==QEvent.Type.KeyPress and watched is self.query:
            if event.key()==Qt.Key.Key_Escape:self.dismiss();return True
            if event.key() in {Qt.Key.Key_Return,Qt.Key.Key_Enter} and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:self.step(-1);return True
        return super().eventFilter(watched,event)

    def refresh(self):
        self.bind();editor=self.editor();self.matches=[];self.index=-1
        if not editor:return
        self.matches,self.limit=text_matches(editor.toPlainText(),self.query.text(),self.case.isChecked())
        editor.search_ranges=self.matches;editor.highlight_lines()
        if self.matches:
            position=editor.textCursor().selectionStart()
            self.index=next((i for i,(a,b) in enumerate(self.matches) if a>=position),0)
            if self._move:self.select()
            else:self.count.setText(f'{len(self.matches)}'+('+' if self.limit else '')+' matches')
        elif self.query.text():self.count.setText('No matches in this file')
        else:self.count.setText('Type to find')

    def select(self):
        if not self.matches:return
        editor=self.editor();start,end=self.matches[self.index];cursor=editor.textCursor();cursor.setPosition(start);cursor.setPosition(end,QTextCursor.MoveMode.KeepAnchor);editor.setTextCursor(cursor);editor.ensureCursorVisible()
        self.count.setText(f'{self.index+1} / {len(self.matches)}'+('+' if self.limit else '')+' matches')

    def step(self,direction):
        if self.timer.isActive():self.timer.stop();self.refresh();return
        if self.matches:self.index=(self.index+direction)%len(self.matches);self.select()

    def dismiss(self):
        self.hide();self.timer.stop()
        if self._bound:self._bound.search_ranges=[];self._bound.highlight_lines();self._bound.setFocus()

class ProjectSearch(QDialog):
    def __init__(self,window,query=''):
        super().__init__(window);self.window=window;self.worker=None;self.pending=False;self.closing=False;self.root=window.snapshot.root;self.setObjectName('formatPreview');self.setWindowTitle('Search project');self.resize(1060,640)
        col=QVBoxLayout(self);col.setContentsMargins(20,18,20,18)
        self.query=QLineEdit();self.query.setPlaceholderText('Search project text…');self.query.setText(query);col.addWidget(self.query)
        self.summary=QLabel('Results include supported text files and unsaved open buffers.');col.addWidget(self.summary)
        self.results=QTreeWidget();self.results.setHeaderLabels(['File','Line','Matching text']);self.results.header().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch);self.results.setColumnWidth(0,300);col.addWidget(self.results,1)
        self.results.itemActivated.connect(self.activate)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(250);self.timer.timeout.connect(self.run)
        self.query.textChanged.connect(lambda:self.timer.start());self.query.returnPressed.connect(self.run)
        if query:self.timer.start()

    def run(self):
        if self.worker:self.pending=True;self.worker.cancel.set();return
        if not self.window.snapshot or self.window.snapshot.root!=self.root:self.summary.setText('Workspace changed. Reopen project search.');return
        query=self.query.text();self.results.clear()
        if not query:self.summary.setText('Type to search supported project text files.');return
        paths=list(self.window.project_files);buffers={doc.path.relative_to(self.root).as_posix():editor.toPlainText() for editor,doc in self.window.documents.items()}
        self.summary.setText('Searching…');worker=Worker(lambda cancel,progress:search_project(self.root,paths,query,buffers=buffers,cancel=cancel),self);self.worker=worker;state={}
        worker.done.connect(lambda result:state.update(result=result));worker.failed.connect(lambda error:state.update(error=error))
        def finished():
            self.worker=None;worker.deleteLater()
            if self.closing:self.close();return
            if self.pending or self.query.text()!=query:self.pending=False;self.run();return
            if 'error' in state:self.summary.setText(state['error']);return
            result=state['result']
            for row in result['rows']:
                item=QTreeWidgetItem(self.results,[row['path'],str(row['line']),row['preview']]);item.setData(0,Qt.ItemDataRole.UserRole,row)
            self.summary.setText(f"{len(result['rows'])}{'+' if result['limited'] else ''} matches · {result['scanned']} files searched · {result['skipped']} files skipped"+(' · Limit reached' if result['limited'] else '')+(' · No matches' if not result['rows'] else '')+' · Double-click a result to open')
        worker.finished.connect(finished);worker.start()

    def activate(self,item,column=0):
        if not self.window.snapshot or self.window.snapshot.root!=self.root:return
        row=item.data(0,Qt.ItemDataRole.UserRole);self.window.open_file(row['path'],row['line']);self.window.navigate(0)
        editor=self.window.current_editor();block=editor.document().findBlockByNumber(row['line']-1);prefix=block.text()[:row['column']]
        start=block.position()+len(prefix.encode('utf-16-le'))//2
        cursor=editor.textCursor();cursor.setPosition(start);cursor.setPosition(min(start+len(self.query.text().encode('utf-16-le'))//2,editor.document().characterCount()-1),QTextCursor.MoveMode.KeepAnchor);editor.setTextCursor(cursor)

    def closeEvent(self,event):
        self.timer.stop()
        if self.worker:self.closing=True;self.worker.cancel.set();event.ignore();return
        super().closeEvent(event)
