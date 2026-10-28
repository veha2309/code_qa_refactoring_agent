"""Quiet workspace backing; no animated or full-window gradient layers."""
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget


class GlassWorkspace(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor('#171b21'))
