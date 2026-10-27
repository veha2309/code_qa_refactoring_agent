"""Native editor, syntax highlighting and paired diff controls."""
import difflib
import keyword
import re

from PySide6.QtCore import Qt, QRect, QSize, Signal, QTimer,QEvent,QStringListModel
from PySide6.QtGui import (QColor, QFont, QPainter, QPen, QPolygon, QSyntaxHighlighter,
    QTextCharFormat, QTextCursor, QKeySequence, QIcon, QPixmap, QPainterPath)
from PySide6.QtWidgets import (QCompleter, QFrame, QHBoxLayout, QLabel, QPlainTextEdit,
    QSplitter, QTextEdit, QVBoxLayout, QWidget)


def icon(name, color="#a0a0a0"):
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if name in {"file", "save"}:
        painter.drawRoundedRect(6, 3, 13, 18, 2, 2)
        painter.drawLine(9, 9, 16, 9)
        painter.drawLine(9, 13, 16, 13)
        painter.drawLine(9, 17, 14, 17)
    elif name == "folder":
        path = QPainterPath()
        path.moveTo(3, 7); path.lineTo(3, 20); path.lineTo(21, 20); path.lineTo(21, 7)
        path.lineTo(12, 7); path.lineTo(9, 4); path.lineTo(3, 4); path.closeSubpath()
        painter.drawPath(path)
    elif name == "code":
        painter.drawLine(8, 7, 3, 12); painter.drawLine(3, 12, 8, 17)
        painter.drawLine(16, 7, 21, 12); painter.drawLine(21, 12, 16, 17)
        painter.drawLine(14, 4, 10, 20)
    elif name == "branch":
        painter.drawEllipse(4, 3, 5, 5); painter.drawEllipse(4, 16, 5, 5); painter.drawEllipse(16, 5, 5, 5)
        painter.drawLine(6, 8, 6, 16); painter.drawLine(7, 13, 18, 10)
    elif name == "impact":
        painter.drawEllipse(9, 9, 6, 6)
        for x, y in [(4, 4), (20, 4), (4, 20), (20, 20)]:
            painter.drawLine(12, 12, x, y); painter.drawEllipse(x-2, y-2, 4, 4)
    elif name == "test":
        painter.drawRoundedRect(4, 3, 16, 18, 3, 3)
        painter.drawLine(7, 12, 11, 16); painter.drawLine(11, 16, 17, 8)
    elif name == "refactor":
        painter.drawLine(4, 7, 18, 7); painter.drawLine(15, 4, 19, 7); painter.drawLine(19, 7, 15, 10)
        painter.drawLine(20, 17, 6, 17); painter.drawLine(9, 14, 5, 17); painter.drawLine(5, 17, 9, 20)
    else:
        painter.drawEllipse(5, 5, 14, 14)
        painter.drawLine(12, 10, 12, 16); painter.drawPoint(12, 7)
    painter.end()
    return QIcon(pixmap)


class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.formats = {}
        for key, color in {"keyword":"#c678dd", "string":"#98c379", "comment":"#7a8087", "number":"#d19a66", "function":"#61afef", "builtin":"#c4c8ce"}.items():
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            if key == "keyword":
                fmt.setFontWeight(QFont.Weight.DemiBold)
            self.formats[key] = fmt

    def highlightBlock(self, text):
        self.setCurrentBlockState(0)
        for match in re.finditer(r"\b(?:" + "|".join(keyword.kwlist) + r")\b", text):
            self.setFormat(match.start(), len(match.group()), self.formats["keyword"])
        for match in re.finditer(r"\b(?:self|cls|str|int|float|bool|list|dict|set|tuple|len|print|range|super|enumerate|zip)\b", text):
            self.setFormat(match.start(), len(match.group()), self.formats["builtin"])
        for match in re.finditer(r"\b\d+(?:\.\d+)?\b", text):
            self.setFormat(match.start(), len(match.group()), self.formats["number"])
        for match in re.finditer(r"\b(?:def|class)\s+(\w+)", text):
            self.setFormat(match.start(1), len(match.group(1)), self.formats["function"])
        spans = []
        for match in re.finditer(r'''(?:[rubfRUBF]{0,2})(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')''', text):
            spans.append((match.start(), match.end()))
            self.setFormat(match.start(), len(match.group()), self.formats["string"])
        for pos, char in enumerate(text):
            if char == "#" and not any(a <= pos < b for a, b in spans):
                self.setFormat(pos, len(text)-pos, self.formats["comment"])
                break
        previous = self.previousBlockState()
        cursor = 0
        if previous in (1, 2):
            delimiter = "'''" if previous == 1 else '"""'
            end = text.find(delimiter)
            if end < 0:
                self.setFormat(0, len(text), self.formats["string"])
                self.setCurrentBlockState(previous)
                return
            self.setFormat(0, end+3, self.formats["string"])
            cursor = end+3
        while cursor < len(text):
            matches = [(text.find(d, cursor), state, d) for state, d in [(1,"'''"),(2,'"""')]]
            matches = [row for row in matches if row[0] >= 0]
            if not matches:
                break
            start, state, delimiter = min(matches)
            end = text.find(delimiter, start+3)
            if end < 0:
                self.setFormat(start, len(text)-start, self.formats["string"])
                self.setCurrentBlockState(state)
                break
            self.setFormat(start, end+3-start, self.formats["string"])
            cursor = end+3


class Gutter(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_gutter(event)


class CodeEditor(QPlainTextEdit):
    completionRequested = Signal()
    automaticCompletionRequested = Signal()
    saveRequested = Signal()
    positionChanged = Signal(str)
    refactorRequested = Signal(str)
    definitionRequested = Signal()
    aiCompletionRequested = Signal()
    formatRequested = Signal()

    def __init__(self, readonly=False):
        super().__init__()
        self.setReadOnly(readonly)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFont("Roboto Mono", 10))
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.highlighter = PythonHighlighter(self.document())
        self.gutter = Gutter(self)
        self.first_line = 1
        self.line_numbers = None
        self.diff_lines = {}
        self.search_ranges=[]
        self.ghost_text=""; self.ai_enabled=False;self.completion_epoch=0
        self.indent_text='    ';self.indent_width=4;self._completion_explicit=True;self._completion_navigated=False
        self.textChanged.connect(self.clear_ghost); self.cursorPositionChanged.connect(self.clear_ghost)
        self.blockCountChanged.connect(self.update_margin)
        self.updateRequest.connect(self.update_gutter)
        self.cursorPositionChanged.connect(self.highlight_lines)
        self.cursorPositionChanged.connect(lambda: self.positionChanged.emit(f"Ln {self.textCursor().blockNumber()+1}, Col {self.textCursor().positionInBlock()+1}"))
        self.completer = QCompleter(self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completion_model=QStringListModel(self);self.completer.setModel(self._completion_model)
        self.completer.activated.connect(self.insert_completion)
        self.completer.popup().installEventFilter(self)
        self.completion_timer = QTimer(self)
        self.completion_timer.setSingleShot(True)
        self.completion_timer.setInterval(400)
        self.completion_timer.timeout.connect(self.automaticCompletionRequested.emit)
        self.ai_timer=QTimer(self); self.ai_timer.setSingleShot(True); self.ai_timer.setInterval(900)
        self.ai_timer.timeout.connect(self.aiCompletionRequested.emit)
        self.update_margin()

    def gutter_width(self):
        return 24 + self.fontMetrics().horizontalAdvance("9") * len(str(max(1, self.blockCount()+self.first_line)))

    def update_margin(self):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def update_gutter(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.gutter.setGeometry(QRect(self.contentsRect().left(), self.contentsRect().top(), self.gutter_width(), self.contentsRect().height()))

    def paint_gutter(self, event):
        painter = QPainter(self.gutter)
        painter.fillRect(event.rect(), QColor("#121c22"))
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        while block.isValid() and top <= event.rect().bottom():
            height = round(self.blockBoundingRect(block).height())
            if block.isVisible() and top + height >= event.rect().top():
                painter.setPen(QColor("#c4c4c4") if block.blockNumber() == self.textCursor().blockNumber() else QColor("#737373"))
                number = self.line_numbers[block.blockNumber()] if self.line_numbers is not None and block.blockNumber()<len(self.line_numbers) else block.blockNumber()+self.first_line
                painter.drawText(0, top, self.gutter.width()-12, self.fontMetrics().height(), Qt.AlignmentFlag.AlignRight, str(number) if number is not None else "")
            top += height
            block = block.next()

    def highlight_lines(self):
        selections = []
        first=self.firstVisibleBlock().position();last=self.document().findBlockByNumber(self.firstVisibleBlock().blockNumber()+max(4,self.viewport().height()//max(1,self.fontMetrics().height())+3))
        stop=last.position() if last.isValid() else self.document().characterCount()
        for start,end in self.search_ranges:
            if end<first or start>stop or end>=self.document().characterCount():continue
            item=QTextEdit.ExtraSelection();item.cursor=QTextCursor(self.document());item.cursor.setPosition(start);item.cursor.setPosition(end,QTextCursor.MoveMode.KeepAnchor);item.format.setBackground(QColor('#5d5530'));item.format.setForeground(QColor('#f4e5b7'));selections.append(item)
        for row, color in self.diff_lines.items():
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(self.document().findBlockByNumber(row))
            selection.format.setBackground(QColor(color))
            selection.format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
            selections.append(selection)
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            selection.format.setBackground(QColor("#1a282f"))
            selection.format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
            selections.append(selection)
        self.setExtraSelections(selections)
        self.gutter.update()

    def set_code(self, code, line=1):
        self.first_line = line
        self.line_numbers = None
        self.setPlainText(code)
        self.document().setModified(False)
        self.update_margin()
        self.configure_indent()

    def configure_indent(self):
        from .indentation import indent_style
        self.indent_text,self.indent_width=indent_style(self.toPlainText(),getattr(self,'_syntax_language','python'))
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ')*self.indent_width)

    def set_language(self,path):
        from .languages import language_for
        language=language_for(path)
        if getattr(self,"_syntax_language","python")==language:self.configure_indent();return
        self.highlighter.setDocument(None); self.highlighter.deleteLater()
        self._syntax_language=language
        if language=="python":self.highlighter=PythonHighlighter(self.document())
        else:
            from .highlighting import ForeignHighlighter
            self.highlighter=ForeignHighlighter(self.document(),path)
        self.configure_indent()

    def goto_line(self, line):
        cursor = QTextCursor(self.document().findBlockByNumber(max(0, line-self.first_line)))
        self.setTextCursor(cursor)
        self.centerCursor()

    def prefix(self):
        cursor=self.textCursor()
        text=cursor.block().text().encode("utf-16-le")[:cursor.positionInBlock()*2].decode("utf-16-le")
        return re.search(r"\w*$", text).group()

    def code_offset(self, position=None):
        position = self.textCursor().position() if position is None else position
        return len(self.toPlainText().encode("utf-16-le")[:position*2].decode("utf-16-le"))

    def clear_ghost(self):
        self.completion_epoch+=1;self.ghost_text=""; self.viewport().update()

    def offer_ghost(self,value):
        cursor=self.textCursor()
        after=cursor.block().text().encode("utf-16-le")[cursor.positionInBlock()*2:].decode("utf-16-le")
        if self.isReadOnly() or not self.hasFocus() or cursor.hasSelection() or after.strip():return False
        self.completer.popup().hide(); self.ghost_text="".join(value.splitlines(keepends=True)[:8])[:1000]; self.viewport().update()
        return bool(self.ghost_text)

    def accept_ghost(self):
        value=self.ghost_text; self.clear_ghost()
        if value and not self.isReadOnly():
            cursor=self.textCursor(); cursor.beginEditBlock(); cursor.insertText(value); cursor.endEditBlock(); self.setTextCursor(cursor)

    def paintEvent(self,event):
        super().paintEvent(event)
        if self.ghost_text:
            painter=QPainter(self.viewport()); painter.setFont(self.font()); painter.setPen(QColor("#788797"))
            rect=self.cursorRect(); height=self.fontMetrics().height(); left=rect.x()
            for index,line in enumerate(self.ghost_text.splitlines()[:8]):
                painter.drawText(left if index==0 else self.contentOffset().x()+12,rect.y()+self.fontMetrics().ascent()+index*height,line)
            painter.end()

    def offer_completions(self, names, explicit=True):
        if not names or not self.hasFocus():
            self.completer.popup().hide()
            return
        self._completion_explicit=explicit;self._completion_navigated=False
        self._completion_model.setStringList(names)
        self.completer.setCompletionPrefix(self.prefix())
        self.completer.popup().setCurrentIndex(self.completer.completionModel().index(0, 0))
        rect = self.cursorRect()
        rect.setWidth(max(250, self.completer.popup().sizeHintForColumn(0)+24))
        self.completer.complete(rect)

    def insert_completion(self, name):
        cursor = self.textCursor()
        cursor.beginEditBlock()
        for _ in self.prefix():
            cursor.deletePreviousChar()
        cursor.insertText(name)
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def eventFilter(self,watched,event):
        if event.type()==QEvent.Type.KeyPress and hasattr(self,'completer') and watched is self.completer.popup():
            if event.key() in {Qt.Key.Key_Up,Qt.Key.Key_Down}:self._completion_navigated=True
            if event.key() in {Qt.Key.Key_Return,Qt.Key.Key_Enter} and not self._completion_explicit and not self._completion_navigated:
                self.completer.popup().hide();self.keyPressEvent(event);return True
        return super().eventFilter(watched,event)

    def line_parts(self):
        cursor=self.textCursor();raw=cursor.block().text().encode('utf-16-le');cut=cursor.positionInBlock()*2
        return raw[:cut].decode('utf-16-le'),raw[cut:].decode('utf-16-le')

    def indent_lines(self,unindent=False):
        cursor=self.textCursor();selected=cursor.hasSelection();start,end=cursor.selectionStart(),cursor.selectionEnd()
        if not selected and not unindent:
            prefix,_=self.line_parts();amount=self.indent_width-len(prefix.expandtabs(self.indent_width))%self.indent_width
            cursor.insertText('\t' if self.indent_text=='\t' else ' '*amount);self.setTextCursor(cursor);return
        first=self.document().findBlock(start);last=self.document().findBlock(end)
        if selected and end==last.position() and last!=first:last=last.previous()
        blocks=[];block=first
        while block.isValid():
            blocks.append((block.position(),block.text()))
            if block==last:break
            block=block.next()
        edit=QTextCursor(self.document());edit.beginEditBlock();delta=0
        for position,text in reversed(blocks):
            edit.setPosition(position)
            if unindent:
                spaces=len(text)-len(text.lstrip(' '));count=1 if text.startswith('\t') else ((spaces-1)%self.indent_width+1 if spaces else 0)
                edit.setPosition(position+count,QTextCursor.MoveMode.KeepAnchor);edit.removeSelectedText();delta-=count
            else:edit.insertText(self.indent_text);delta+=len(self.indent_text)
        edit.endEditBlock()
        if selected:
            edit.setPosition(first.position());edit.setPosition(max(first.position(),end+delta),QTextCursor.MoveMode.KeepAnchor)
        else:edit.setPosition(max(first.position(),start+delta))
        self.setTextCursor(edit)

    def smart_newline(self):
        from .indentation import code_tail
        cursor=self.textCursor();cursor.beginEditBlock()
        if cursor.hasSelection():cursor.removeSelectedText();self.setTextCursor(cursor)
        prefix,suffix=self.line_parts();indent=re.match(r'[ \t]*',prefix).group()
        language=getattr(self,'_syntax_language','python');tail=code_tail(prefix,language)
        increase=tail in {'(','[','{'} or language=='python' and tail==':'
        pairs={'(':')','[':']','{':'}'}
        between=tail in pairs and suffix.lstrip().startswith(pairs[tail])
        if between:
            spaces=len(suffix)-len(suffix.lstrip(' \t'))
            cursor.setPosition(cursor.position()+spaces,QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText('\n'+indent+self.indent_text+'\n'+indent)
            cursor.movePosition(QTextCursor.MoveOperation.Left,QTextCursor.MoveMode.MoveAnchor,len(indent)+1)
        else:cursor.insertText('\n'+indent+(self.indent_text if increase else ''))
        cursor.endEditBlock();self.setTextCursor(cursor)

    def keyPressEvent(self, event):
        self.completion_timer.stop()
        if self.ghost_text and event.key()==Qt.Key.Key_Tab:
            self.accept_ghost(); return
        if self.ghost_text and event.key()==Qt.Key.Key_Escape:
            self.clear_ghost(); return
        if event.key() in {Qt.Key.Key_Return,Qt.Key.Key_Enter} and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.aiCompletionRequested.emit(); return
        self.clear_ghost(); self.ai_timer.stop()
        if self.completer.popup().isVisible() and event.key() in {Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Escape, Qt.Key.Key_Tab, Qt.Key.Key_Backtab}:
            event.ignore()
            return
        if event.matches(QKeySequence.StandardKey.Save):
            self.saveRequested.emit()
            return
        if event.key() == Qt.Key.Key_F12:
            self.definitionRequested.emit()
            return
        if event.key() == Qt.Key.Key_Space and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.completionRequested.emit()
            return
        if not self.isReadOnly() and event.key() == Qt.Key.Key_Tab and not self.textCursor().hasSelection() and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.indent_lines()
            return
        if not self.isReadOnly() and event.key() in {Qt.Key.Key_Tab,Qt.Key.Key_Backtab}:
            self.indent_lines(event.key()==Qt.Key.Key_Backtab or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier));return
        if not self.isReadOnly() and event.key()==Qt.Key.Key_Backspace and not self.textCursor().hasSelection():
            prefix,_=self.line_parts()
            if prefix and not prefix.strip():
                count=1 if prefix.endswith('\t') else (len(prefix.expandtabs(self.indent_width))-1)%self.indent_width+1
                cursor=self.textCursor();cursor.beginEditBlock()
                for _ in range(min(count,len(prefix))):cursor.deletePreviousChar()
                cursor.endEditBlock();self.setTextCursor(cursor);return
        if not self.isReadOnly() and event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            self.smart_newline()
            if self.ai_enabled:self.ai_timer.start()
            return
        super().keyPressEvent(event)
        if not self.isReadOnly():
            if self.ai_enabled and (event.text() or event.key() in {Qt.Key.Key_Backspace,Qt.Key.Key_Delete}):
                self.ai_timer.start()
            elif event.text() and (event.text().isalnum() and len(self.prefix()) >= 2 or event.text() == "."):
                self.completion_timer.start()

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        if not self.isReadOnly():
            menu.addSeparator()
            menu.addAction("Format document   Alt+Shift+F",self.formatRequested.emit)
            menu.addAction("Go to definition   F12", self.definitionRequested.emit)
            menu.addAction("Complete Python   Ctrl+Space", self.completionRequested.emit)
            menu.addSeparator()
            menu.addAction("Rename symbol…", lambda: self.refactorRequested.emit("rename"))
            for title, operation in [("Extract helper…", "extract_method"), ("Extract variable…", "extract_variable")]:
                item = menu.addAction(title, lambda checked=False, op=operation: self.refactorRequested.emit(op))
                item.setEnabled(self.textCursor().hasSelection())
        menu.exec(event.globalPos())


class DiffViewer(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.caption = QLabel("Choose a changed file to compare versions.")
        self.caption.setObjectName("diffCaption")
        layout.addWidget(self.caption)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.before, self.after = CodeEditor(True), CodeEditor(True)
        for title, editor in [("BASE VERSION", self.before), ("WORKING VERSION", self.after)]:
            panel = QWidget()
            column = QVBoxLayout(panel)
            column.setContentsMargins(0, 0, 0, 0)
            label = QLabel(title)
            label.setObjectName("eyebrow")
            column.addWidget(label)
            column.addWidget(editor)
            splitter.addWidget(panel)
        layout.addWidget(splitter, 1)
        self._syncing = False
        self.before.verticalScrollBar().valueChanged.connect(lambda value: self.sync(self.after, value))
        self.after.verticalScrollBar().valueChanged.connect(lambda value: self.sync(self.before, value))
        self.diff = ""

    def sync(self, target, value):
        if not self._syncing:
            self._syncing = True
            target.verticalScrollBar().setValue(value)
            self._syncing = False

    def set_versions(self, before, after, caption=""):
        if caption:self.before.set_language(caption); self.after.set_language(caption)
        old, new = before.splitlines(), after.splitlines()
        removed, added = set(), set()
        left, right, left_numbers, right_numbers = [], [], [], []
        for tag, a, b, c, d in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
            for offset in range(max(b-a,d-c)):
                row=len(left)
                has_old,has_new=a+offset<b,c+offset<d
                left.append(old[a+offset] if has_old else "")
                right.append(new[c+offset] if has_new else "")
                left_numbers.append(a+offset+1 if has_old else None)
                right_numbers.append(c+offset+1 if has_new else None)
                if tag!="equal" and has_old:removed.add(row)
                if tag!="equal" and has_new:added.add(row)
        self.before.set_code("\n".join(left)); self.after.set_code("\n".join(right))
        self.before.line_numbers,self.after.line_numbers=left_numbers,right_numbers
        self.before.diff_lines = {row: "#3b202b" for row in removed}
        self.after.diff_lines = {row: "#15382e" for row in added}
        self.before.highlight_lines(); self.after.highlight_lines()
        self.caption.setText(f"{caption}    +{len(added)} added   -{len(removed)} removed")
        if removed:
            self.before.setTextCursor(QTextCursor(self.before.document().findBlockByNumber(min(removed))))
        if added:
            self.after.setTextCursor(QTextCursor(self.after.document().findBlockByNumber(min(added))))
        self.diff = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True)))

    def toPlainText(self):
        return self.diff

    def clear(self):
        self.set_versions("", "")
