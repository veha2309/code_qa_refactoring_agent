"""Optional native XYZ impact explorer, alongside the flat and layered maps."""
import math
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtGui import QColor,QPainter,QPen,QFont,QPainterPath
from .lens3d import SpatialLens
from .polyglot import INFERRED_KINDS


class PerspectiveLens(SpatialLens):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.label_hits=[]
        self.setToolTip('3D · fixed node positions · click to inspect · drag empty space to orbit · right-drag to pan · wheel to zoom · Home resets')

    def reset_view(self):
        self.yaw=-.35;self.pitch=.22;self.zoom=1.;self.pan=QPointF();self.update()

    def set_records(self,rows,edges,locations,root):
        super().set_records(rows,edges,locations,root)
        groups={}
        for row in rows:groups.setdefault(row['distance'],[]).append(row)
        self.positions={}
        for distance,group in sorted(groups.items()):
            count=len(group);columns=2 if count>1 else 1;levels=math.ceil(count/columns)
            for i,row in enumerate(sorted(group,key=lambda r:r['symbol'])):
                self.positions[row['symbol']]=[distance*330.,(i//columns-(levels-1)/2)*155.,(i%columns-(columns-1)/2)*240.]
        if self.positions:
            center=(min(p[0] for p in self.positions.values())+max(p[0] for p in self.positions.values()))/2
            for p in self.positions.values():p[0]-=center
        self.reset_view()

    def rotate(self,p):
        x,y,z=p;cy,sy=math.cos(self.yaw),math.sin(self.yaw);x,z=x*cy+z*sy,-x*sy+z*cy
        cp,sp=math.cos(self.pitch),math.sin(self.pitch)
        return x,y*cp-z*sp,y*sp+z*cp

    def project(self,p):
        rotated=[self.rotate(v) for v in self.positions.values()]
        sx=max((abs(v[0]) for v in rotated),default=250)*2+360;sy=max((abs(v[1]) for v in rotated),default=160)*2+220
        scale=min((self.width()-80)/max(600,sx),(self.height()-170)/max(380,sy))*self.zoom
        x,y,z=self.rotate(p);perspective=1500/max(500,1500+z);scale*=perspective
        return QPointF(self.width()/2+self.pan.x()+x*scale,self.height()/2+20+self.pan.y()+y*scale),z,scale

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.fillRect(self.rect(),QColor('#181e26'))
        self.hitboxes=[];self.label_hits=[];self.visible_labels=[]
        projected={sid:self.project(pos) for sid,pos in self.positions.items()}
        p.setClipRect(QRectF(0,72,self.width(),max(0,self.height()-105)))
        for distance in sorted({r['distance'] for r in self.rows.values()}):
            points=[self.positions[sid] for sid,r in self.rows.items() if r['distance']==distance]
            if not points:continue
            x=points[0][0];lo=min(v[1] for v in points)-70;hi=max(v[1] for v in points)+70
            corners=[self.project((x,y,z))[0] for y,z in [(lo,-170),(lo,170),(hi,170),(hi,-170)]]
            plane=QPainterPath(corners[0])
            for corner in corners[1:]:plane.lineTo(corner)
            plane.closeSubpath();p.setPen(QPen(QColor(111,151,164,65),1));p.setBrush(QColor(70,102,116,14));p.drawPath(plane)
        for e in self.edges:
            if e['caller'] not in projected or e['callee'] not in projected:continue
            a,b=projected[e['callee']][0],projected[e['caller']][0];active=e['caller'] in self.active and e['callee'] in self.active
            p.setOpacity(.85 if active else .13);pen=QPen(QColor('#8baea9'),1.6)
            if e['kind'] in INFERRED_KINDS:pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen);p.setBrush(Qt.BrushStyle.NoBrush);path=QPainterPath(a);dx=b.x()-a.x();path.cubicTo(a.x()+dx*.4,a.y(),b.x()-dx*.4,b.y(),b.x(),b.y());p.drawPath(path)
            tip=path.pointAtPercent(.66);prev=path.pointAtPercent(.64);vx,vy=tip.x()-prev.x(),tip.y()-prev.y();length=max(1,math.hypot(vx,vy));ux,uy=vx/length,vy/length
            p.drawLine(tip,QPointF(tip.x()-ux*8-uy*3,tip.y()-uy*8+ux*3));p.drawLine(tip,QPointF(tip.x()-ux*8+uy*3,tip.y()-uy*8-ux*3))
        occupied=[]
        for sid,(point,depth,scale) in sorted(projected.items(),key=lambda item:-item[1][1]):
            selected=sid in {self.selected,self.hovered};color=QColor('#e2b38b' if self.rows[sid]['distance']==0 else '#a5c9aa' if self.locations.get(sid,{}).get('is_test') else '#92bcb9')
            radius=max(6,min(12,9*scale));p.setOpacity(1 if sid in self.active else .3);p.setBrush(color);p.setPen(QPen(color.lighter(130),1));p.drawEllipse(point,radius,radius)
            if selected:p.setBrush(Qt.BrushStyle.NoBrush);p.drawEllipse(point,radius+4,radius+4)
            rect=QRectF(point.x()-radius-5,point.y()-radius-5,2*radius+10,2*radius+10);occupied.append(rect);self.hitboxes.append((rect,sid))
        font=QFont('Noto Sans');font.setPixelSize(12);p.setFont(font)
        priority=sorted(projected,key=lambda sid:(sid!=self.hovered,sid!=self.selected,self.rows[sid]['distance'],sid))
        for sid in priority:
            if len(self.visible_labels)>=20 and sid not in {self.selected,self.hovered}:continue
            point=projected[sid][0];rect=None
            for dx,dy in [(19,-26),(-209,-26),(-95,-78),(-95,30),(35,-96),(-225,45)]:
                trial=QRectF(point.x()+dx,point.y()+dy,190,52)
                if trial.left()<8 or trial.right()>self.width()-8 or trial.top()<80 or trial.bottom()>self.height()-38:continue
                if not any(trial.intersects(other) for other in occupied):rect=trial;break
            if rect is None:continue
            occupied.append(rect);self.visible_labels.append(sid);self.label_hits.append((rect,sid))
            p.setOpacity(1 if sid in self.active else .4);p.setPen(QPen(QColor('#627b80'),1));p.drawLine(point,rect.center());p.setBrush(QColor('#25323c'));p.drawRoundedRect(rect,5,5)
            p.setPen(QColor('#dfebe6'));font.setPixelSize(12);p.setFont(font);name=sid.split(':',1)[-1]
            p.drawText(rect.adjusted(9,5,-8,-25),Qt.AlignmentFlag.AlignVCenter,p.fontMetrics().elidedText(name,Qt.TextElideMode.ElideRight,173))
            font.setPixelSize(10);p.setFont(font);p.setPen(QColor('#9caeb8'));loc=self.locations.get(sid,{})
            path=loc.get('path',sid.split(':',1)[0])+':'+str(loc.get('start',''))
            p.drawText(rect.adjusted(9,27,-8,-5),Qt.AlignmentFlag.AlignVCenter,p.fontMetrics().elidedText(path,Qt.TextElideMode.ElideMiddle,173))
        p.setClipping(False);p.setOpacity(1);p.fillRect(QRectF(0,0,self.width(),70),QColor('#181e26'));p.setPen(QColor('#dde8e3'));font.setPixelSize(13);p.setFont(font)
        p.drawText(18,25,'3D impact explorer · same source evidence as the other maps');font.setPixelSize(11);p.setFont(font);p.setPen(QColor('#9aadb8'))
        name=self.hovered or self.selected;identity=name if name in self.rows else 'Choose a function to explore'
        p.drawText(18,49,p.fontMetrics().elidedText(identity,Qt.TextElideMode.ElideMiddle,max(50,self.width()-35)))
        p.fillRect(QRectF(0,self.height()-30,self.width(),30),QColor('#181e26'));p.drawText(18,self.height()-10,f'{len(self.rows)} nodes · {len(self.visible_labels)} labels · drag to orbit · right-drag to pan · wheel to zoom · Home resets');p.end()

    def node_at(self,point):
        if point.y()<72 or point.y()>self.height()-30:return None
        return next((sid for rect,sid in reversed(self.hitboxes+self.label_hits) if rect.contains(point)),None)

    def mousePressEvent(self,event):
        self.setFocus();sid=self.node_at(event.position());self.drag=('pan',None) if event.button()==Qt.MouseButton.RightButton else ('select',sid) if sid else ('orbit',None);self.last=event.position()
        if sid and event.button()==Qt.MouseButton.LeftButton:self.select_node(sid)
        event.accept()

    def mouseMoveEvent(self,event):
        if not self.drag:
            sid=self.node_at(event.position())
            if sid!=self.hovered:self.hovered=sid;self.update()
            self.setCursor(Qt.CursorShape.PointingHandCursor if sid else Qt.CursorShape.OpenHandCursor);return
        delta=event.position()-self.last;self.last=event.position();mode,sid=self.drag
        if mode=='orbit':self.yaw+=delta.x()*.007;self.pitch=max(-1.1,min(1.1,self.pitch+delta.y()*.007))
        elif mode=='pan':self.pan+=delta
        self.update();event.accept()

    def wheelEvent(self,event):self.zoom=max(.3,min(2.5,self.zoom*(1.12 if event.angleDelta().y()>0 else 1/1.12)));self.update();event.accept()

    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Home:self.reset_view();return
        if event.key() in {Qt.Key.Key_Left,Qt.Key.Key_Right}:self.yaw+=-.12 if event.key()==Qt.Key.Key_Left else .12;self.update();return
        if event.key() in {Qt.Key.Key_Up,Qt.Key.Key_Down}:self.pitch=max(-1.1,min(1.1,self.pitch+(-.12 if event.key()==Qt.Key.Key_Up else .12)));self.update();return
        if event.key() in {Qt.Key.Key_Return,Qt.Key.Key_Space} and self.selected:self.activated.emit(self.selected);return
        super().keyPressEvent(event)
