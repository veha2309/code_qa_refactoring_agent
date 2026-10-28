"""Native editable design canvas. Edits are drafts, never source-analysis facts."""
from copy import deepcopy
import json
import textwrap
import uuid
from pathlib import Path
from PySide6.QtCore import Qt,QRectF,QPointF,Signal,QTimer
from PySide6.QtGui import QColor,QPainter,QPen,QFont,QPainterPath,QKeySequence,QUndoStack,QUndoCommand
from PySide6.QtWidgets import (QWidget,QHBoxLayout,QVBoxLayout,QGraphicsView,QGraphicsScene,QGraphicsObject,QGraphicsItem,QGraphicsPathItem,QGraphicsSimpleTextItem,QLineEdit,QPlainTextEdit,QLabel,QPushButton,QComboBox,QSplitter,QFileDialog,QMessageBox)
from PySide6.QtSvg import QSvgGenerator


def extracted_model(report,level,scope=None,page=0,include_aux=False):
    from .design_diagrams import candidates,scopes,scope_for,ordered_records,class_edges,PAGE_SIZE
    nodes=[];edges=[]
    if level=='HLD':
        groups=scopes(report,include_aux);chosen=groups[page*PAGE_SIZE:(page+1)*PAGE_SIZE]
        for i,group in enumerate(chosen):
            rows=candidates(report,group,include_aux)
            nodes.append({'id':group,'title':group,'kind':'package','path':'','line':1,
                'fields':[f'{len({r["path"] for r in rows})} files',f'{len(rows)} declarations'],
                'operations':sorted({r['name'] for r in rows})[:6],'x':(i%2)*510,'y':(i//2)*330,'origin':'extracted'})
        ids=set(chosen);seen={}
        for edge in report['dependencies']:
            a,b=scope_for(edge['from']),scope_for(edge['to'])
            if a!=b and a in ids and b in ids:
                kind=edge['classification'];seen.setdefault((a,b),[]).append(kind)
        for (a,b),kinds in seen.items():edges.append({'id':str(uuid.uuid4()),'from':a,'to':b,'label':'depends on','classification':'resolved static' if 'resolved static' in kinds else 'inferred','origin':'extracted'})
    else:
        rows=ordered_records(report,scope,include_aux)[page*PAGE_SIZE:(page+1)*PAGE_SIZE]
        members={}
        for s in report['symbols']:members.setdefault(s.get('owner'),[]).append(s)
        heights=[0,0]
        for i,row in enumerate(rows):
            operations=row.get('constructors',[])+row.get('enum_values',[])+[m.get('signature') or m['name']+'(…) [signature unavailable]' for m in sorted(members.get(row['id'],[]),key=lambda r:r['start'])]
            if not operations and row.get('signature'):operations=[row['signature']]
            node={'id':row['id'],'title':row['name'],'kind':row.get('declaration_kind',row['kind']),
                'path':row['path'],'line':row['start'],'fields':[f"{f['name']}: {f['annotation']}" for f in row.get('fields',[])],
                'operations':operations,'bases':row.get('bases',[]),'x':(i%2)*510,'y':heights[i%2],'origin':'extracted'}
            nodes.append(node);heights[i%2]+=node_height(node)+70
        ids={r['id'] for r in nodes}
        for a,b,kind,count in class_edges(report):
            if a in ids and b in ids:edges.append({'id':str(uuid.uuid4()),'from':a,'to':b,'label':'declared type' if kind.startswith('declared') else 'references','classification':kind,'evidence_count':count,'origin':'extracted'})
    return {'format':'changelens-design','version':1,'snapshot_id':report['snapshot_id'],'project':report['project'],
        'level':level,'scope':scope,'page':page,'nodes':nodes,'edges':edges,'notice':'Editable design draft. User changes are not verified source evidence.'}


def lines_for(node):
    fields=[part for value in node.get('fields',[]) for part in textwrap.wrap(value,44) or ['']]
    operations=[part for value in node.get('operations',[]) for part in textwrap.wrap(value,44,subsequent_indent='  ') or ['']]
    return fields,operations


def node_height(node):
    fields,operations=lines_for(node)
    return max(125,100+18*(len(fields)+len(operations))+int(bool(fields and operations))*16+len(node.get('bases',[]))*18)


class DesignNode(QGraphicsObject):
    def __init__(self,canvas,record):
        super().__init__();self.canvas=canvas;self.record=record;self.start=None
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable|QGraphicsItem.GraphicsItemFlag.ItemIsSelectable|QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setPos(record['x'],record['y']);self.setToolTip(record['id']+'\n'+record['origin'])

    def boundingRect(self):return QRectF(0,0,365,node_height(self.record))

    def paint(self,p,option,widget=None):
        r=self.record;rect=self.boundingRect();p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color='#92bfae' if r['origin']=='extracted' else '#c6a676'
        p.setPen(QPen(QColor(color if self.isSelected() else '#435967'),2 if self.isSelected() else 1));p.setBrush(QColor('#232e39'));p.drawRoundedRect(rect,7,7)
        font=QFont('Noto Sans');font.setPixelSize(14);p.setFont(font);p.setPen(QColor('#e3ece8'))
        p.drawText(QRectF(14,10,335,23),Qt.AlignmentFlag.AlignVCenter,p.fontMetrics().elidedText(r['title'],Qt.TextElideMode.ElideRight,330))
        font.setPixelSize(11);p.setFont(font);p.setPen(QColor(color));p.drawText(14,50,r['kind']+' · '+('CODE' if r['origin']=='extracted' else 'USER DRAFT'))
        p.setPen(QColor('#93a8b6'));p.drawText(14,69,p.fontMetrics().elidedText(r.get('path',''),Qt.TextElideMode.ElideMiddle,330))
        y=91;font=QFont('Roboto Mono');font.setPixelSize(12);p.setFont(font)
        for base in r.get('bases',[]):p.setPen(QColor('#bcaad1'));p.drawText(14,y,'base: '+base[:44]);y+=18
        fields,operations=lines_for(r);p.setPen(QColor('#c5d6df'))
        for value in fields:p.drawText(14,y,value);y+=18
        if fields and operations:p.setPen(QPen(QColor('#43535f'),1));p.drawLine(14,y-6,350,y-6);y+=16;p.setPen(QColor('#c5d6df'))
        for value in operations:p.drawText(14,y,value);y+=18

    def itemChange(self,change,value):
        result=super().itemChange(change,value)
        if change==QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.canvas:self.canvas.update_edges()
        return result

    def mousePressEvent(self,event):self.start=self.pos();super().mousePressEvent(event)

    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event)
        if self.start is not None and self.pos()!=self.start:
            # Qt moves every selected movable item. Commit the entire scene
            # delta before the undo command rebuilds it, not only this card.
            positions={sid:(item.pos().x(),item.pos().y()) for sid,item in self.canvas.nodes.items()
                       if item.pos()!=QPointF(item.record['x'],item.record['y'])}
            if positions:self.canvas.groupMoveRequested.emit(positions)
        self.start=None


class ModelCommand(QUndoCommand):
    def __init__(self,canvas,before,after,title):super().__init__(title);self.canvas=canvas;self.before=before;self.after=after
    def undo(self):self.canvas.restore(self.before)
    def redo(self):self.canvas.restore(self.after)


class CanvasView(QGraphicsView):
    def __init__(self,scene,canvas):super().__init__(scene);self.canvas=canvas
    def wheelEvent(self,event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor=1.12 if event.angleDelta().y()>0 else 1/1.12
            if .08<self.transform().m11()*factor<4:self.scale(factor,factor)
            event.accept();return
        super().wheelEvent(event)
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Space:
            self.setInteractive(False);self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag);event.accept();return
        if event.matches(QKeySequence.StandardKey.Undo):self.canvas.history.undo();return
        if event.matches(QKeySequence.StandardKey.Redo):self.canvas.history.redo();return
        if event.key()==Qt.Key.Key_Delete:self.canvas.delete_selected();return
        super().keyPressEvent(event)
    def keyReleaseEvent(self,event):
        if event.key()==Qt.Key.Key_Space:self.setInteractive(True);self.setDragMode(QGraphicsView.DragMode.RubberBandDrag);event.accept();return
        super().keyReleaseEvent(event)


class EditableDesign(QWidget):
    moveRequested=Signal(str,object)
    groupMoveRequested=Signal(object)
    codeRequested=Signal(str,int)
    changed=Signal()

    def __init__(self,parent=None):
        super().__init__(parent);self.model=None;self.nodes={};self.edges=[];self.history=QUndoStack(self);self.selection_id=None
        col=QVBoxLayout(self);col.setContentsMargins(0,0,0,0)
        self.toolbar=QWidget();tools=QHBoxLayout(self.toolbar);tools.setContentsMargins(0,0,0,0)
        for name,cb in [('Add card',lambda:self.add_node('package' if self.model and self.model['level']=='HLD' else 'class')),('Note',lambda:self.add_node('note')),('Delete',self.delete_selected),('Undo',self.history.undo),('Redo',self.history.redo),('Fit',self.fit),('Save design',self.save_design),('Load design',self.load_design),('Export SVG',self.export_svg)]:
            b=QPushButton(name);b.clicked.connect(cb);tools.addWidget(b)
        col.addWidget(self.toolbar)
        self.notice=QLabel('Move cards to arrange the design. Edit details or add proposed relationships in the inspector. Drafts do not change source code.');self.notice.setWordWrap(True);self.notice.setObjectName('muted');col.addWidget(self.notice)
        split=QSplitter();col.addWidget(split,1)
        self.scene=QGraphicsScene(self);self.view=CanvasView(self.scene,self);self.view.setRenderHint(QPainter.RenderHint.Antialiasing);self.view.setBackgroundBrush(QColor('#171d25'));self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag);split.addWidget(self.view)
        editor=QWidget();self.inspector=editor;editor.setMaximumWidth(310);side=QVBoxLayout(editor)
        side.addWidget(QLabel('SELECTED CARD / RELATIONSHIP'));self.title=QLineEdit();side.addWidget(self.title)
        side.addWidget(QLabel('Fields · one per line'));self.fields=QPlainTextEdit();self.fields.setMaximumHeight(130);side.addWidget(self.fields)
        side.addWidget(QLabel('Operations / note text · one per line'));self.operations=QPlainTextEdit();side.addWidget(self.operations,1)
        apply=QPushButton('Apply draft edit');apply.clicked.connect(self.apply_properties);side.addWidget(apply)
        code=QPushButton('Open source');code.clicked.connect(self.open_source);side.addWidget(code)
        side.addWidget(QLabel('PROPOSED RELATIONSHIP'));self.source=QComboBox();self.target=QComboBox();side.addWidget(self.source);side.addWidget(self.target)
        self.edge_kind=QComboBox();self.edge_kind.addItems(['depends on','association','inherits','calls']);side.addWidget(self.edge_kind)
        connect=QPushButton('Add relationship');connect.clicked.connect(self.add_edge);side.addWidget(connect);split.addWidget(editor);split.setSizes([850,290])
        self.scene.selectionChanged.connect(self.selection_changed);self.moveRequested.connect(self.move_node,Qt.ConnectionType.QueuedConnection)
        self.groupMoveRequested.connect(self.move_nodes,Qt.ConnectionType.QueuedConnection)
        self.history.indexChanged.connect(self.history_changed)

    def history_changed(self,index):self.changed.emit()

    def set_model(self,model):
        self.history.blockSignals(True);self.history.clear();self.restore(model);self.history.blockSignals(False);self.changed.emit()

    def restore(self,model):
        selected=self.selection_id
        selected_nodes={item.record['id'] for item in self.scene.selectedItems() if isinstance(item,DesignNode)}
        self.scene.blockSignals(True);self.scene.clear();self.nodes={};self.edges=[];self.model=deepcopy(model)
        if self.model:
            for r in self.model['nodes']:
                item=DesignNode(self,r);self.nodes[r['id']]=item;self.scene.addItem(item)
            for r in self.model['edges']:
                edge=QGraphicsPathItem();edge.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable);edge.setData(0,r['id']);edge.setZValue(-1);self.scene.addItem(edge)
                label=QGraphicsSimpleTextItem(r['label']);label.setBrush(QColor('#9cafbd'));label.setZValue(-.5);self.scene.addItem(label);self.edges.append((edge,label,r))
            self.update_edges()
        self.scene.blockSignals(False);self.source.clear();self.target.clear()
        for r in (self.model or {}).get('nodes',[]):self.source.addItem(r['title'],r['id']);self.target.addItem(r['title'],r['id'])
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-70,-70,70,70));self.selection_id=None;self.title.clear();self.fields.clear();self.operations.clear()
        for sid in selected_nodes:
            if sid in self.nodes:self.nodes[sid].setSelected(True)
        if not selected_nodes and selected in self.nodes:self.nodes[selected].setSelected(True)
        if not self.scene.selectedItems():self.inspector.hide()
        self.notice.setText('Editable '+(self.model or {}).get('level','design')+' · snapshot '+(self.model or {}).get('snapshot_id','')+' · CODE cards are extracted; USER DRAFT cards and connectors are proposals. Save design preserves this page, including all details and evidence classifications.')

    def update_edges(self):
        for item,label,r in self.edges:
            a,b=self.nodes.get(r['from']),self.nodes.get(r['to'])
            if not a or not b:continue
            right=b.pos().x()>=a.pos().x();x=a.pos().x()+(365 if right else 0);u=b.pos().x()+(0 if right else 365);y=a.pos().y()+45;v=b.pos().y()+45
            if a.pos().x()==b.pos().x():
                below=b.pos().y()>a.pos().y();x=a.pos().x()+182.5;u=x;y=a.pos().y()+(a.boundingRect().height() if below else 0);v=b.pos().y()+(0 if below else b.boundingRect().height())
                path=QPainterPath(QPointF(x,y));mid=(y+v)/2;path.cubicTo(x,mid,u,mid,u,v)
            else:
                path=QPainterPath(QPointF(x,y));bend=max(80,abs(u-x)*.5);sign=1 if right else -1;path.cubicTo(x+sign*bend,y,u-sign*bend,v,u,v)
            tip=path.pointAtPercent(1);prev=path.pointAtPercent(.98);delta=tip-prev;length=max(1,(delta.x()**2+delta.y()**2)**.5);dx,dy=delta.x()/length,delta.y()/length
            path.moveTo(tip);path.lineTo(tip.x()-dx*9-dy*4,tip.y()-dy*9+dx*4);path.moveTo(tip);path.lineTo(tip.x()-dx*9+dy*4,tip.y()-dy*9-dx*4)
            item.setPath(path);pen=QPen(QColor('#8daea9' if r['origin']=='extracted' else '#c6a676'),1.5)
            if r.get('classification')!='resolved static' or r['origin']!='extracted':pen.setStyle(Qt.PenStyle.DashLine)
            item.setPen(pen);item.setToolTip(r['label']+' · '+r['origin']+' · '+r.get('classification','user proposal'))
            label.setText(r['label']);mid=path.pointAtPercent(.5);label.setPos(mid.x()-label.boundingRect().width()/2,mid.y()-20)

    def transaction(self,title,mutate):
        if not self.model:return
        before=deepcopy(self.model);after=deepcopy(before);mutate(after)
        if before!=after:self.history.push(ModelCommand(self,before,after,title))

    def move_node(self,sid,pos):
        if not self.model or not any(r['id']==sid for r in self.model['nodes']):return
        self.transaction('Move card',lambda m:next(r for r in m['nodes'] if r['id']==sid).update(x=pos.x(),y=pos.y()))

    def move_nodes(self,positions):
        if not self.model:return
        ids={r['id'] for r in self.model['nodes']}
        positions={sid:xy for sid,xy in positions.items() if sid in ids}
        if not positions:return
        def move(model):
            for row in model['nodes']:
                if row['id'] in positions:row.update(x=positions[row['id']][0],y=positions[row['id']][1])
        self.transaction('Move selected cards' if len(positions)>1 else 'Move card',move)

    def selection_changed(self):
        selected=self.scene.selectedItems()
        if not selected:return
        item=selected[0]
        if isinstance(item,DesignNode):
            self.inspector.show()
            r=item.record;self.selection_id=r['id'];self.title.setText(r['title']);self.fields.setPlainText('\n'.join(r.get('fields',[])));self.operations.setPlainText('\n'.join(r.get('operations',[])))
        elif item.data(0):
            self.inspector.show()
            self.selection_id=item.data(0);r=next((r for r in self.model['edges'] if r['id']==self.selection_id),None)
            if r:self.title.setText(r['label']);self.fields.clear();self.operations.setPlainText(r.get('classification','user proposal'))

    def apply_properties(self):
        sid=self.selection_id
        if not sid:return
        title=self.title.text().strip()[:500];fields=[v[:9999] for v in self.fields.toPlainText().splitlines()[:500]];ops=[v[:9999] for v in self.operations.toPlainText().splitlines()[:500]]
        def mutate(m):
            for r in m['nodes']:
                if r['id']==sid:
                    r.setdefault('original',deepcopy(r));r.update(title=title,fields=fields,operations=ops,origin='edited');return
            for r in m['edges']:
                if r['id']==sid:r.setdefault('original',deepcopy(r));r.update(label=title,origin='edited',classification='user proposal')
        self.transaction('Edit design detail',mutate)

    def add_node(self,kind):
        if not self.model or len(self.model['nodes'])>=200:self.notice.setText('This canvas supports up to 200 cards.');return
        center=self.view.mapToScene(self.view.viewport().rect().center());sid='user:'+str(uuid.uuid4())
        self.transaction('Add '+kind,lambda m:m['nodes'].append({'id':sid,'title':'New '+kind,'kind':kind,'fields':[],'operations':['Describe this design decision'] if kind=='note' else [],'x':center.x(),'y':center.y(),'origin':'user','path':'','line':1}))
        if sid in self.nodes:self.nodes[sid].setSelected(True)

    def add_edge(self):
        if not self.model or len(self.model['edges'])>=1000:return
        a,b=self.source.currentData(),self.target.currentData()
        if not a or not b or a==b:return
        self.transaction('Add proposed relationship',lambda m:m['edges'].append({'id':'user:'+str(uuid.uuid4()),'from':a,'to':b,'label':self.edge_kind.currentText(),'classification':'user proposal','origin':'user'}))

    def delete_selected(self):
        ids={i.record['id'] if isinstance(i,DesignNode) else i.data(0) for i in self.scene.selectedItems()}
        self.transaction('Delete design items',lambda m:(m.update(nodes=[r for r in m['nodes'] if r['id'] not in ids]),m.update(edges=[r for r in m['edges'] if r['id'] not in ids and r['from'] not in ids and r['to'] not in ids])))

    def open_source(self):
        if self.model and self.model['snapshot_id']!=getattr(self,'expected_snapshot',self.model['snapshot_id']):
            self.notice.setText('Historical draft: source navigation is disabled because this snapshot differs from the current review.');return
        row=next((r for r in (self.model or {}).get('nodes',[]) if r['id']==self.selection_id),None)
        if row and row.get('path'):self.codeRequested.emit(row['path'],row.get('line',1))

    def frame_readable(self):
        bounds=self.scene.itemsBoundingRect().adjusted(-30,-30,30,30)
        if bounds.isEmpty():return
        scale=min(1.,max(.7,(self.view.viewport().width()-30)/max(1,bounds.width())))
        self.view.resetTransform();self.view.scale(scale,scale)
        self.view.centerOn(bounds.center().x(),bounds.top()+self.view.viewport().height()/(2*scale))

    def fit(self):self.view.fitInView(self.scene.itemsBoundingRect().adjusted(-30,-30,30,30),Qt.AspectRatioMode.KeepAspectRatio)

    def save_design(self):
        if not self.model:return
        filename,_=QFileDialog.getSaveFileName(self,'Save editable design','','Change Lens design (*.cldesign.json)')
        if filename:
            if not filename.lower().endswith('.json'):filename+='.cldesign.json'
            try:Path(filename).write_text(json.dumps(self.model,ensure_ascii=False,indent=2),encoding='utf-8');self.history.setClean();self.notice.setText('Saved editable design: '+filename)
            except OSError as exc:QMessageBox.warning(self,'Save design',str(exc))

    def load_design(self):
        filename,_=QFileDialog.getOpenFileName(self,'Load editable design','','Change Lens design (*.json)')
        if not filename:return
        try:
            if Path(filename).stat().st_size>10_000_000:raise ValueError('Design file exceeds 10 MB.')
            value=json.loads(Path(filename).read_text(encoding='utf-8'))
            validate_model(value)
            if self.model and value['snapshot_id']!=self.model['snapshot_id']:
                QMessageBox.information(self,'Historical design','This design belongs to a different source snapshot. It will open as a draft; its relationships are not current verified evidence.')
            self.set_model(value);self.changed.emit();self.fit()
        except (OSError,ValueError,KeyError,TypeError) as exc:QMessageBox.warning(self,'Load design',str(exc))

    def export_svg(self):
        if not self.model:return
        filename,_=QFileDialog.getSaveFileName(self,'Export current design SVG','','SVG (*.svg)')
        if filename:
            try:self.write_svg(filename)
            except OSError as exc:QMessageBox.warning(self,'Export SVG',str(exc))

    def write_svg(self,filename):
        generator=QSvgGenerator();generator.setFileName(str(filename));bounds=self.scene.itemsBoundingRect().adjusted(-25,-55,25,25);generator.setViewBox(bounds);generator.setSize(bounds.size().toSize())
        generator.setTitle('Editable '+self.model['level']+' design draft');generator.setDescription('Snapshot '+self.model['snapshot_id']+'; user edits are proposals, not verified code facts.')
        painter=QPainter(generator)
        if not painter.isActive():raise OSError('Unable to write the SVG file.')
        painter.fillRect(bounds,QColor('#171d25'));self.scene.render(painter,bounds,bounds);painter.setPen(QColor('#dce5df'));painter.drawText(QPointF(bounds.left()+12,bounds.top()+24),'DESIGN DRAFT · '+self.model['level']+' · snapshot '+self.model['snapshot_id']);painter.end()


def validate_model(value):
    import math
    if value.get('format')!='changelens-design' or value.get('version')!=1:raise ValueError('Unsupported design file.')
    if value.get('level') not in {'HLD','LLD'}:raise ValueError('Missing HLD / LLD level.')
    if not isinstance(value.get('snapshot_id'),str):raise ValueError('Missing snapshot identity.')
    nodes=value['nodes'];edges=value['edges']
    if not isinstance(nodes,list) or not isinstance(edges,list) or len(nodes)>200 or len(edges)>1000:raise ValueError('Design exceeds editor limits (200 nodes / 1,000 edges).')
    ids=set()
    for r in nodes:
        if not all(isinstance(r.get(k),str) and len(r[k])<=2000 for k in ['id','title','kind','origin']):raise ValueError('Invalid card identity or title.')
        if r['id'] in ids:raise ValueError('Duplicate card identity.')
        ids.add(r['id'])
        if not all(isinstance(r.get(k),(int,float)) and math.isfinite(r[k]) and abs(r[k])<1000000 for k in ['x','y']):raise ValueError('Invalid card position.')
        if not isinstance(r.get('bases',[]),list) or not all(isinstance(v,str) and len(v)<2000 for v in r.get('bases',[])):raise ValueError('Invalid base declarations.')
        for k in ['fields','operations']:
            if not isinstance(r.get(k),list) or len(r[k])>500 or not all(isinstance(v,str) and len(v)<10000 for v in r[k]):raise ValueError('Invalid member detail.')
    for r in edges:
        if not all(isinstance(r.get(k),str) for k in ['id','from','to','label','origin']) or len(r['label'])>2000 or r['from'] not in ids or r['to'] not in ids:raise ValueError('Invalid relationship endpoints.')
