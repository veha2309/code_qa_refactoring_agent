"""Keyboard-first file and command picker, without executing project code."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QLabel


class Picker(QDialog):
    def __init__(self, parent, title, entries):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setObjectName("commandPicker")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.resize(620, 380)
        self.entries = entries
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self.query = QLineEdit()
        self.query.setPlaceholderText(title)
        layout.addWidget(self.query)
        self.hint = QLabel("↑ ↓ to navigate · Enter to open · Esc to close")
        self.hint.setObjectName("muted")
        layout.addWidget(self.hint)
        self.results = QListWidget()
        layout.addWidget(self.results, 1)
        self.query.textChanged.connect(self.filter)
        self.query.returnPressed.connect(self.activate)
        self.results.itemActivated.connect(self.activate)
        self.query.installEventFilter(self)
        self.filter("")

    def filter(self, query):
        self.results.clear()
        words = query.casefold().split()
        for label, callback in self.entries:
            if all(word in label.casefold() for word in words):
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, callback)
                self.results.addItem(item)
        self.results.setCurrentRow(0)
        count = self.results.count()
        self.hint.setText(f"{count} results · ↑ ↓ to navigate · Enter to open · Esc to close" if count else "No matches. Try a shorter name or a different word.")

    def eventFilter(self, watched, event):
        if event.type() == event.Type.KeyPress and event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            offset = 1 if event.key() == Qt.Key.Key_Down else -1
            self.results.setCurrentRow(max(0, min(self.results.count()-1, self.results.currentRow()+offset)))
            return True
        return super().eventFilter(watched, event)

    def activate(self, *args):
        item = self.results.currentItem()
        if item:
            callback = item.data(Qt.ItemDataRole.UserRole)
            self.accept()
            callback()
