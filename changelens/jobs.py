"""Cooperative background work for the native interface."""
from threading import Event
from PySide6.QtCore import QThread, Signal
from .core import Cancelled


class Worker(QThread):
    message = Signal(str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.task = task
        self.cancel = Event()

    def run(self):
        try:
            self.done.emit(self.task(self.cancel, self.message.emit))
        except Cancelled:
            self.failed.emit("Operation cancelled. Review the current workspace before continuing.")
        except Exception as exc:
            self.failed.emit(str(exc) or type(exc).__name__)
