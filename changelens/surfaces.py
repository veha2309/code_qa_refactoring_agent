"""Lightweight native glass surfaces; editor text is never blurred."""
from PySide6.QtCore import QPointF,QRectF
from PySide6.QtGui import QColor,QPainter,QLinearGradient,QRadialGradient
from PySide6.QtWidgets import QWidget


class GlassWorkspace(QWidget):
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        base=QLinearGradient(0,0,self.width(),self.height());base.setColorAt(0,QColor('#17242a'));base.setColorAt(1,QColor('#10171d'));painter.fillRect(self.rect(),base)
        for point,radius,color in [(QPointF(self.width()*.12,-80),650,QColor(82,153,145,33)),(QPointF(self.width()*.95,self.height()*.85),580,QColor(187,126,91,18))]:
            glow=QRadialGradient(point,radius);glow.setColorAt(0,color);glow.setColorAt(1,QColor(0,0,0,0));painter.fillRect(self.rect(),glow)
