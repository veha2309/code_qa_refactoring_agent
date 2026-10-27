"""Short native transitions. Live editors keep their normal paint/input path."""
import os
from contextlib import contextmanager
from functools import wraps
from PySide6.QtCore import Qt,QEasingCurve,QPropertyAnimation,QVariantAnimation,QRectF
from PySide6.QtGui import QPainter,QColor
from PySide6.QtWidgets import QApplication,QStackedWidget,QListWidget,QGraphicsOpacityEffect


def enabled():
    app=QApplication.instance()
    return os.environ.get('CHANGELENS_REDUCE_MOTION')!='1' and not (app and app.property('reduceMotion'))


class AnimatedStack(QStackedWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.overlay=None;self.transition=None

    def setCurrentIndex(self,index):
        if index==self.currentIndex():return
        self.finish_transition()
        super().setCurrentIndex(index)

    def finish_transition(self):
        if self.transition:self.transition.stop();self.transition.deleteLater();self.transition=None
        if self.overlay:self.overlay.hide();self.overlay.deleteLater();self.overlay=None

    def resizeEvent(self,event):
        self.finish_transition();super().resizeEvent(event)


class AnimatedNavigation(QListWidget):
    """Move a small marker, never fade, capture or resize the editor content."""
    def __init__(self,parent=None):
        super().__init__(parent);self.marker=None;self.target=None
        self.motion=QVariantAnimation(self);self.motion.setDuration(160);self.motion.setEasingCurve(QEasingCurve.Type.OutCubic);self.motion.valueChanged.connect(self.set_marker)

    def set_marker(self,value):self.marker=float(value);self.viewport().update()

    def glide_to_current(self):
        item=self.currentItem()
        if item is None:return
        rect=self.visualItemRect(item)
        if not rect.isValid():return
        target=rect.center().x()-20
        if self.target==target:return
        self.target=target;self.motion.stop()
        if self.marker is None or not enabled():self.set_marker(target);return
        self.motion.setStartValue(self.marker);self.motion.setEndValue(float(target));self.motion.start()

    def stop_motion(self):
        self.motion.stop()
        if self.target is not None:self.set_marker(self.target)

    def paintEvent(self,event):
        super().paintEvent(event)
        if self.currentItem() is None:return
        rect=self.visualItemRect(self.currentItem())
        if not rect.isValid():return
        if self.marker is None:self.marker=rect.center().x()-20
        painter=QPainter(self.viewport());painter.setRenderHint(QPainter.RenderHint.Antialiasing);painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#a8d3bf'));painter.drawRoundedRect(QRectF(self.marker,rect.bottom()-3,40,2),1,1)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'motion'):self.marker=None;self.target=None;self.glide_to_current()


@contextmanager
def paint_transaction(widget):
    active=widget.updatesEnabled()
    if active:widget.setUpdatesEnabled(False)
    try:yield
    finally:
        if active:widget.setUpdatesEnabled(True);widget.update()


def atomic_paint(function):
    @wraps(function)
    def wrapped(self,*args,**kwargs):
        with paint_transaction(self):return function(self,*args,**kwargs)
    return wrapped


def reveal(widget):
    """Fade a drawer once; remove the effect so its code stays crisp afterward."""
    previous=getattr(widget,'_reveal_animation',None)
    if previous:previous.stop()
    widget.show()
    if not enabled():return
    effect=QGraphicsOpacityEffect(widget);widget.setGraphicsEffect(effect)
    animation=QPropertyAnimation(effect,b'opacity',widget);animation.setDuration(170);animation.setStartValue(.25);animation.setEndValue(1.0);animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    widget._reveal_animation=animation
    def done():
        if getattr(widget,'_reveal_animation',None) is animation:
            widget._reveal_animation=None;widget.setGraphicsEffect(None)
        animation.deleteLater()
    animation.finished.connect(done);animation.start()
