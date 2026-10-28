"""Readable depth layers replacing the orbiting sphere graph.

The compatibility class name is retained; the view has fixed, shallow depth,
full code cards, and pan/zoom rather than a camera the user must manipulate.
"""
import math
from PySide6.QtCore import Qt,QPointF,QRectF,Signal
from PySide6.QtGui import QColor,QPainter,QPen,QFont,QPainterPath
from PySide6.QtWidgets import QWidget
from .polyglot import INFERRED_KINDS


class SpatialLens(QWidget):
    activated=Signal(str)

    def __init__(self,parent=None):
        super().__init__(parent);self.setMinimumSize(360,310);self.setFocusPolicy(Qt.FocusPolicy.StrongFocus);self.setMouseTracking(True)
        self.positions={};self.rows={};self.edges=[];self.locations={};self.root=None;self.selected=None;self.active=set();self.hitboxes=[];self.visible_labels=[];self.drag=None;self.hovered=None
        self.reset_view()
        self.setToolTip('Dependency layers · drag to pan · wheel to zoom · Home to fit. Arrows show potential impact, from a dependency to its callers.')

    def reset_view(self):
        self.zoom=1.;self.pan=QPointF();self.update()

    def set_records(self,rows,edges,locations,root):
        self.rows={r['symbol']:r for r in rows};self.edges=edges;self.locations=locations;self.root=root;self.selected=root;self.hovered=None;self.positions={}
        groups={}
        for row in rows:groups.setdefault(row['distance'],[]).append(row)
        for distance,group in sorted(groups.items()):
            for i,row in enumerate(sorted(group,key=lambda r:r['symbol'])):
                self.positions[row['symbol']]=[distance*330.,i*120.,distance*14.]
        self.select_node(root,False);self.reset_view()

    def project(self,position):
        max_x=max((v[0] for v in self.positions.values()),default=330)
        scale=min(1.,max(.65,(self.width()-80)/max(560,max_x+260)))*self.zoom
        x,y,z=position
        return QPointF(28+self.pan.x()+(x+z*.18)*scale,104+self.pan.y()+y*scale),z,scale

    def select_node(self,sid,emit=True):
        if sid not in self.rows:
            self.active=set(self.rows);return
        self.selected=sid;self.active={sid};pending=[sid]
        while pending:
            target=pending.pop()
            for e in self.edges:
                if e['caller']==target and e['callee'] not in self.active:self.active.add(e['callee']);pending.append(e['callee'])
        if sid==self.root:self.active=set(self.rows)
        self.update()
        if emit:self.activated.emit(sid)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.fillRect(self.rect(),QColor('#181e26'));self.hitboxes=[];self.visible_labels=[]
        projected={sid:self.project(pos) for sid,pos in self.positions.items()};cards={sid:QRectF(point.x(),point.y(),244*scale,86*scale) for sid,(point,z,scale) in projected.items()}
        p.setClipRect(QRectF(0,78,self.width(),self.height()-110))
        for distance in sorted({r['distance'] for r in self.rows.values()}):
            ids=[sid for sid,r in self.rows.items() if r['distance']==distance]
            if not ids:continue
            rect=cards[ids[0]];p.setPen(QColor('#8b9fae'));font=QFont('Noto Sans');font.setPixelSize(12);p.setFont(font)
            p.drawText(QPointF(rect.left(),rect.top()-15),'Selected source' if distance==0 else f'{distance} reference hop'+('s' if distance!=1 else ''))
        for e in self.edges:
            a,b=cards.get(e['callee']),cards.get(e['caller'])
            if a is None or b is None:continue
            active=e['caller'] in self.active and e['callee'] in self.active;p.setOpacity(.85 if active else .12)
            pen=QPen(QColor('#88aaa8'),1.6)
            if e['kind'] in INFERRED_KINDS:pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen);p.setBrush(Qt.BrushStyle.NoBrush);start=QPointF(a.right(),a.center().y());end=QPointF(b.left(),b.center().y());path=QPainterPath(start)
            if b.left()<=a.left():
                end=QPointF(b.right(),b.center().y());bend=max(a.right(),b.right())+30;path.cubicTo(bend,start.y(),bend,end.y(),end.x(),end.y())
            else:path.cubicTo(start.x()+42,start.y(),end.x()-42,end.y(),end.x(),end.y())
            p.drawPath(path);tip=path.pointAtPercent(1);prior=path.pointAtPercent(.98);dx,dy=tip.x()-prior.x(),tip.y()-prior.y();length=max(1,math.hypot(dx,dy));ux,uy=dx/length,dy/length
            p.drawLine(tip,QPointF(tip.x()-ux*8-uy*3,tip.y()-uy*8+ux*3));p.drawLine(tip,QPointF(tip.x()-ux*8+uy*3,tip.y()-uy*8-ux*3))
        for sid,rect in cards.items():
            p.setOpacity(1 if sid in self.active else .28);selected=sid in {self.selected,self.hovered};r=self.rows[sid];loc=self.locations.get(sid,{})
            color=QColor('#e2b38b' if r['distance']==0 else '#a5c9aa' if loc.get('is_test') else '#92bcb9')
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(0,0,0,45));p.drawRoundedRect(rect.translated(4,5),6,6)
            p.setBrush(QColor('#26343d' if selected else '#222c35'));p.setPen(QPen(color if selected else QColor('#41545f'),1.6 if selected else 1));p.drawRoundedRect(rect,6,6)
            p.setPen(color);font=QFont('Noto Sans');font.setPixelSize(10);p.setFont(font);p.drawText(rect.adjusted(12,7,-10,-50),'SOURCE' if r['distance']==0 else 'TEST' if loc.get('is_test') else 'DEPENDENT CODE')
            font.setPixelSize(13);p.setFont(font);p.setPen(QColor('#e1ebe6'));name=sid.split(':',1)[-1]
            p.drawText(rect.adjusted(12,25,-10,-20),Qt.AlignmentFlag.AlignVCenter,p.fontMetrics().elidedText(name,Qt.TextElideMode.ElideRight,int(rect.width()-24)))
            font.setPixelSize(10);p.setFont(font);p.setPen(QColor('#a1b2b9'));location=loc.get('path',sid.split(':',1)[0])+':'+str(loc.get('start',''))
            p.drawText(rect.adjusted(12,rect.height()-22,-10,-5),Qt.AlignmentFlag.AlignVCenter,p.fontMetrics().elidedText(location,Qt.TextElideMode.ElideMiddle,int(rect.width()-24)))
            self.hitboxes.append((rect,sid))
            if rect.intersects(QRectF(0,78,self.width(),self.height()-110)):self.visible_labels.append(sid)
        p.setClipping(False);p.setOpacity(1);p.fillRect(QRectF(0,0,self.width(),74),QColor('#181e26'));p.setPen(QColor('#dde8e3'));font=QFont('Noto Sans');font.setPixelSize(13);p.setFont(font)
        p.drawText(18,27,'Dependency layers · potential impact →');p.setPen(QColor('#95a8b4'));font.setPixelSize(11);p.setFont(font);p.drawText(18,50,'Selected code → direct references → transitive callers. Solid: resolved; dashed: inferred.')
        p.fillRect(QRectF(0,self.height()-30,self.width(),30),QColor('#181e26'));p.drawText(18,self.height()-10,f'{len(self.rows)} cards · {len(self.visible_labels)} in view · drag to pan · wheel to zoom · Home resets')
        if not self.rows:p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'Choose a function to explore its potential impact.')
        self.label_hits=list(self.hitboxes)
        p.end()

    def node_at(self,point):return next((sid for rect,sid in reversed(self.hitboxes) if rect.contains(point) and 78<point.y()<self.height()-30),None)
    def mousePressEvent(self,event):
        self.setFocus();self.drag=event.position();sid=self.node_at(event.position())
        if sid and event.button()==Qt.MouseButton.LeftButton:self.select_node(sid)
        event.accept()
    def mouseMoveEvent(self,event):
        if self.drag is not None:self.pan+=event.position()-self.drag;self.drag=event.position();self.update()
        else:
            self.hovered=self.node_at(event.position());self.setCursor(Qt.CursorShape.PointingHandCursor if self.hovered else Qt.CursorShape.OpenHandCursor);self.update()
    def mouseReleaseEvent(self,event):self.drag=None;event.accept()
    def wheelEvent(self,event):self.zoom=max(.7,min(2.,self.zoom*(1.12 if event.angleDelta().y()>0 else 1/1.12)));self.update();event.accept()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Home:self.reset_view();return
        directions={Qt.Key.Key_Left:(30,0),Qt.Key.Key_Right:(-30,0),Qt.Key.Key_Up:(0,30),Qt.Key.Key_Down:(0,-30)}
        if event.key() in directions:self.pan+=QPointF(*directions[event.key()]);self.update();return
        if event.key() in {Qt.Key.Key_Return,Qt.Key.Key_Space} and self.selected:self.activated.emit(self.selected);return
        super().keyPressEvent(event)
