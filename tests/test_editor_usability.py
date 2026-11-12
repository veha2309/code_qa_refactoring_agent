"""Keyboard contracts for the native editor, independent of language models."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from changelens.widgets import CodeEditor


def editor(source, path='example.py'):
    app = QApplication.instance() or QApplication([])
    widget = CodeEditor(); widget.set_language(path); widget.set_code(source)
    widget.show(); widget.setFocus(); app.processEvents()
    return app, widget


def test_home_toggle_and_shift_selection():
    app, widget = editor('    value = 1')
    widget.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClick(widget, Qt.Key.Key_Home)
    assert widget.textCursor().positionInBlock() == 4
    QTest.keyClick(widget, Qt.Key.Key_Home, Qt.KeyboardModifier.ShiftModifier)
    assert widget.textCursor().selectedText() == '    '
    widget.close()


def test_multiline_comment_roundtrip_and_single_undo():
    app, widget = editor('  first();\n    second();\n\nnext();', 'a.ts')
    cursor = widget.textCursor(); cursor.setPosition(0); cursor.setPosition(widget.document().findBlockByNumber(3).position(), QTextCursor.MoveMode.KeepAnchor); widget.setTextCursor(cursor)
    original = widget.toPlainText()
    widget.toggle_comment()
    commented = widget.toPlainText()
    assert commented.startswith('  // first();\n  //   second();\n\n')
    assert commented.endswith('next();')
    widget.undo(); assert widget.toPlainText() == original
    widget.redo(); assert widget.toPlainText() == commented
    cursor = widget.textCursor(); cursor.setPosition(0); cursor.setPosition(widget.document().findBlockByNumber(3).position(), QTextCursor.MoveMode.KeepAnchor); widget.setTextCursor(cursor)
    widget.toggle_comment(); assert widget.toPlainText() == original
    widget.close()


def test_duplicate_unicode_line_preserves_column_and_undo():
    app, widget = editor('name = "😀"')
    widget.moveCursor(QTextCursor.MoveOperation.End)
    column = widget.textCursor().positionInBlock()
    QTest.keyClick(widget, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert widget.toPlainText() == 'name = "😀"\nname = "😀"'
    assert widget.textCursor().positionInBlock() == column
    widget.undo(); assert widget.toPlainText() == 'name = "😀"'
    widget.setReadOnly(True); widget.duplicate_text(); widget.toggle_comment()
    assert widget.toPlainText() == 'name = "😀"'
    widget.close()


def test_zoom_updates_tab_stops_without_changing_source():
    app, widget = editor('  const value = 1;', 'a.ts')
    widget.zoom_reset(); before = widget.tabStopDistance()
    widget.zoom_in(); app.processEvents()
    assert widget.font().pixelSize() == 15
    assert widget.tabStopDistance() > before
    widget.zoom_reset(); assert widget.font().pixelSize() == 14
    assert widget.toPlainText() == '  const value = 1;'
    widget.close()
