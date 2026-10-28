"""A native, evidence-backed change map. No generated relationships."""
from PySide6.QtCore import Qt, QRectF, Signal,QEvent,QVariantAnimation,QEasingCurve
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen,QLinearGradient
from PySide6.QtWidgets import (QComboBox, QFrame, QGraphicsItem, QGraphicsObject,
    QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QPushButton, QSplitter,
    QVBoxLayout, QWidget, QPlainTextEdit, QStackedWidget, QLineEdit, QListWidget, QListWidgetItem,QCheckBox)

from .widgets import CodeEditor
from .polyglot import INFERRED_KINDS

INFERRED = INFERRED_KINDS
ALL_CHANGES='__all_changes__'


def map_records(report, root, limit=36):
    rows=sorted((row for row in report.get("impact",[]) if row["path"] and (root==ALL_CHANGES or row["path"][0]==root)),key=lambda row:(row["distance"],row["symbol"]))
    visible=rows[:limit]; ids={row["symbol"] for row in visible}
    edges={}
    for row in visible:
        for edge in row["evidence"]:
            if edge["caller"] in ids and edge["callee"] in ids:
                edges[(edge["caller"],edge["callee"],edge["line"],edge["kind"])]=edge
    # A shortest-path witness is not the whole graph. Preserve parallel routes
    # such as shared component -> login/register -> app.
    for edge in report.get('graph_edges',[]):
        if edge['caller'] in ids and edge['callee'] in ids:
            edges[(edge['caller'],edge['callee'],edge['line'],edge['kind'])]=edge
    return visible,list(edges.values()),len(rows)-len(visible)


class MapNode(QGraphicsObject):
    def __init__(self, sid, label, location, role, activated):
        super().__init__()
        self.sid,self.label,self.location,self.role=sid,label,location,role
        self.activated=activated; self.focused=False
        self.hover_amount=0.0;self.hover_animation=QVariantAnimation(self);self.hover_animation.setDuration(130);self.hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic);self.hover_animation.valueChanged.connect(self.set_hover)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        self.setAcceptHoverEvents(True); self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(sid+"\n"+location+"\nClick to inspect the evidence; Enter selects this node.")

    def boundingRect(self):return QRectF(0,0,204,88)

    def paint(self,painter,option,widget=None):
        colors={"SOURCE":("#edbc9d","#3c3532"),"CODE":("#9dcecc","#253c44"),"TEST":("#b5d9ba","#2c433b")}
        accent,fill=colors[self.role]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(0,0,0,30));painter.drawRoundedRect(QRectF(2,4,200,83),12,12)
        painter.setPen(QPen(QColor(accent if self.focused or self.hover_amount>.05 else "#496260"),1.6 if self.focused else 1+self.hover_amount*.5))
        glass=QLinearGradient(0,0,204,88);upper=QColor(fill);upper.setAlpha(228);lower=QColor('#17282f');lower.setAlpha(235)
        upper=upper.lighter(100+int(self.hover_amount*16));glass.setColorAt(0,upper);glass.setColorAt(1,lower)
        painter.setBrush(glass); painter.drawRoundedRect(QRectF(1,1,202,83),11,11)
        painter.setPen(QPen(QColor(206,235,223,42),1));painter.drawLine(14,2,188,2)
        painter.setPen(QColor(accent)); painter.drawEllipse(QRectF(13,14,9,9))
        painter.setFont(QFont("Noto Sans",8)); painter.drawText(30,22,self.role)
        painter.setPen(QColor("#e0e3df")); painter.setFont(QFont("Noto Sans",10))
        painter.drawText(13,46,QFontMetrics(painter.font()).elidedText(self.label,Qt.TextElideMode.ElideRight,178))
        painter.setPen(QColor("#9ba8ab")); painter.setFont(QFont("Noto Sans",8))
        painter.drawText(13,69,QFontMetrics(painter.font()).elidedText(self.location,Qt.TextElideMode.ElideMiddle,178))

    def mousePressEvent(self,event):
        self.setFocus(); self.activated(self.sid); event.accept()

    def set_hover(self,value):self.hover_amount=float(value);self.update()

    def hoverEnterEvent(self,event):
        from .motion import enabled
        self.hover_animation.stop()
        if enabled():self.hover_animation.setStartValue(self.hover_amount);self.hover_animation.setEndValue(1.0);self.hover_animation.start()
        else:self.set_hover(1)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self,event):
        from .motion import enabled
        self.hover_animation.stop()
        if enabled():self.hover_animation.setStartValue(self.hover_amount);self.hover_animation.setEndValue(0.0);self.hover_animation.start()
        else:self.set_hover(0)
        super().hoverLeaveEvent(event)

    def keyPressEvent(self,event):
        if event.key() in {Qt.Key.Key_Return,Qt.Key.Key_Enter,Qt.Key.Key_Space}:self.activated(self.sid); event.accept()
        else:super().keyPressEvent(event)


class ImpactMap(QGraphicsView):
    activated=Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("impactMap"); self.setScene(QGraphicsScene(self)); self.nodes={}; self.edges=[]
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(480,310)

    def drawBackground(self,painter,rect):
        painter.fillRect(rect,QColor('#1b2129'))
        painter.setPen(QPen(QColor(134,184,176,30),1))
        left=int(rect.left())//32*32; top=int(rect.top())//32*32
        for x in range(left,int(rect.right())+32,32):
            for y in range(top,int(rect.bottom())+32,32):painter.drawPoint(x,y)

    def set_records(self,rows,edges,locations,root):
        self.scene().clear(); self.nodes={}; self.edges=[]
        self.root=root; self.paths={row["symbol"]:row for row in rows}
        groups={"SOURCE":[],"CODE":[],"TEST":[]}
        for row in rows:
            role="SOURCE" if row["symbol"]==root or root==ALL_CHANGES and row['distance']==0 else "TEST" if locations.get(row["symbol"],{}).get("is_test") else "CODE"
            groups[role].append(row)
        for column,(role,title) in enumerate([("SOURCE","FOCUS"),("CODE","AFFECTED CODE"),("TEST","LINKED TESTS")]):
            heading=self.scene().addSimpleText(title,QFont("Noto Sans",8)); heading.setBrush(QColor("#94a3a5")); heading.setPos(20+column*240,22)
            if rows and not groups[role]:
                empty=self.scene().addSimpleText("No path resolved",QFont("Noto Sans",9)); empty.setBrush(QColor("#829193")); empty.setPos(20+column*240,92)
            for index,row in enumerate(groups[role]):
                sid=row["symbol"]; location=locations.get(sid,{})
                value=f"{location.get('path',sid.split(':',1)[0])}:{location.get('start','')}"
                label=location.get("path",sid) if location.get("kind")=="module" else sid.split(":",1)[-1]
                node=MapNode(sid,label,value,role,self.select_node)
                y=80+index*112 if role!="SOURCE" or len(groups['SOURCE'])>1 else 80+max(0,min(4,max(len(groups["CODE"]),len(groups["TEST"]))-1))*56
                self.scene().addItem(node); node.setPos(20+column*240,y); self.nodes[sid]=node
        lanes={};ports={}
        for edge in edges:
            start=self.nodes.get(edge["callee"]); end=self.nodes.get(edge["caller"])
            if not start or not end:continue
            a=start.pos(); b=end.pos(); path=QPainterPath(); path.moveTo(a.x()+204,a.y()+44)
            if a.x()==b.x():
                lane=lanes.get(a.x(),0);lanes[a.x()]=lane+1
                port=ports.get(edge['caller'],0);ports[edge['caller']]=port+1
                bend=a.x()+234+lane*16;end_y=b.y()+34+(port%3)*10
                path.cubicTo(bend,a.y()+44,bend,end_y,b.x()+204,end_y)
            else:path.cubicTo(a.x()+244,a.y()+44,b.x()-40,b.y()+44,b.x(),b.y()+44)
            pen=QPen(QColor("#778c8b"),1.4)
            if edge["kind"] in INFERRED:pen.setStyle(Qt.PenStyle.DashLine)
            item=self.scene().addPath(path,pen); item.setZValue(-1)
            item.setToolTip(f"{edge['caller']} → {edge['callee']}\nLine {edge['line']}: {edge['expression']} ({edge['kind']})")
            self.edges.append((item,edge))
        if not rows:
            empty=self.scene().addText("Choose a function above, then trace its potential impact.",QFont("Noto Sans",11))
            empty.setDefaultTextColor(QColor("#aab8b9")); empty.setPos(30,130)
        self.setSceneRect(self.scene().itemsBoundingRect().adjusted(-16,-12,28,32)); self.reset_map()

    def select_node(self,sid):
        row=self.paths.get(sid,{})
        focused={sid};path_edges=set();pending=[sid]
        while pending:
            target=pending.pop()
            for _,edge in self.edges:
                if edge['caller']!=target:continue
                path_edges.add((edge['caller'],edge['callee'],edge['line'],edge['kind']))
                if edge['callee'] not in focused:focused.add(edge['callee']);pending.append(edge['callee'])
        if sid==self.root:focused=set(self.nodes)
        for key,node in self.nodes.items():node.focused=key==sid; node.setOpacity(1.0 if key in focused else .35); node.update()
        for item,edge in self.edges:
            key=(edge["caller"],edge["callee"],edge["line"],edge["kind"])
            active=sid==self.root or key in path_edges
            item.setOpacity(1.0 if active else .2)
            pen=item.pen(); pen.setWidthF(2 if active and sid!=self.root else 1.4); item.setPen(pen)
        self.activated.emit(sid)

    def reset_map(self):
        self.resetTransform(); factor=min(1.0,max(.7,(self.viewport().width()-18)/740))
        self.scale(factor,factor); self.horizontalScrollBar().setValue(0); self.verticalScrollBar().setValue(0)

    def resizeEvent(self,event):
        super().resizeEvent(event); self.reset_map()

    def wheelEvent(self,event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor=1.12 if event.angleDelta().y()>0 else 1/1.12
            if .45<self.transform().m11()*factor<1.8:self.scale(factor,factor)
            event.accept()
        else:super().wheelEvent(event)


class ChangeLens(QWidget):
    traceRequested=Signal(str)
    codeRequested=Signal(str)
    explainRequested=Signal(str)
    focusUpdated=Signal()

    def __init__(self):
        super().__init__(); self.snapshot=self.report=None; self.selected_sid=None; self.rows={}; self.linked_tests=set()
        layout=QVBoxLayout(self); layout.setContentsMargins(0,0,0,0); layout.setSpacing(12)
        heading=QHBoxLayout(); self.title=QLabel("Follow the change."); self.title.setObjectName("lensTitle"); heading.addWidget(self.title,1)
        self.focus=QComboBox(); self.focus.setMinimumWidth(240); self.focus.setMaximumWidth(400); self.focus.activated.connect(self.focus_changed); heading.addWidget(self.focus)
        self.trace=QPushButton("Trace function"); self.trace.clicked.connect(self.trace_current); heading.addWidget(self.trace); layout.addLayout(heading)
        search_row=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('Find a component, function or file…');self.search.setClearButtonEnabled(True);self.search.installEventFilter(self);self.search.textChanged.connect(self.search_components);self.search.returnPressed.connect(self.activate_search);search_row.addWidget(self.search,1)
        self.search_count=QLabel('');search_row.addWidget(self.search_count);layout.addLayout(search_row)
        self.inferred=QCheckBox('Include inferred links');self.inferred.setToolTip('Include broad scope, callback, historical and framework inferences. These are potential relationships, not resolved calls.');self.inferred.toggled.connect(lambda:self.show_root(self.focus.currentData()));search_row.addWidget(self.inferred)
        self.search_results=QListWidget();self.search_results.setMaximumHeight(185);self.search_results.itemActivated.connect(self.activate_search);self.search_results.itemClicked.connect(self.activate_search);self.search_results.hide();layout.addWidget(self.search_results)
        self.summary=QLabel("Start with a function. See which code and tests depend on it."); self.summary.setWordWrap(True); self.summary.setObjectName("muted"); layout.addWidget(self.summary)
        self.map=ImpactMap(); self.map.activated.connect(self.inspect)
        from .lens3d import SpatialLens
        self.spatial_map=SpatialLens();self.spatial_map.activated.connect(self.spatial_selected)
        self.map_stack=QStackedWidget();self.map_stack.addWidget(self.map);self.map_stack.addWidget(self.spatial_map)
        from .perspective_lens import PerspectiveLens
        self.perspective_map=PerspectiveLens();self.perspective_map.activated.connect(self.spatial_selected);self.map_stack.addWidget(self.perspective_map)
        self.mode=QComboBox();self.mode.addItems(['Impact map','Layers','3D']);self.mode.setToolTip('Choose the flat map, fixed dependency layers or an optional orbitable 3D explorer; all share the same source evidence')
        self.mode.currentIndexChanged.connect(self.change_projection);heading.addWidget(self.mode)
        fit=QPushButton("Fit map"); self.fit_button=fit; fit.clicked.connect(self.fit_map); heading.addWidget(fit)
        split=QSplitter(Qt.Orientation.Horizontal); split.addWidget(self.map_stack)
        detail=QFrame(); self.detail=detail; detail.setObjectName("lensEvidence"); detail.setMinimumWidth(240); detail.setMaximumWidth(330)
        info=QVBoxLayout(detail); info.setContentsMargins(18,16,14,14); info.setSpacing(12)
        tag_row=QHBoxLayout(); tag=QLabel("EVIDENCE"); tag.setObjectName("eyebrow"); tag_row.addWidget(tag,1)
        close=QPushButton("Hide"); close.setObjectName("smallButton"); close.clicked.connect(detail.hide); tag_row.addWidget(close); info.addLayout(tag_row)
        self.node_title=QLabel("Choose a node"); self.node_title.setWordWrap(True); self.node_title.setObjectName("sectionTitle"); info.addWidget(self.node_title)
        self.node_location=QLabel(""); self.node_location.setWordWrap(True); self.node_location.setObjectName("muted"); info.addWidget(self.node_location)
        self.reason=QPlainTextEdit(); self.reason.setReadOnly(True); self.reason.setObjectName("lensReason"); self.reason.setMaximumHeight(190); info.addWidget(self.reason)
        for label in (self.node_title,self.node_location):label.setTextFormat(Qt.TextFormat.PlainText)
        self.source=CodeEditor(True); self.source.setMinimumHeight(100); info.addWidget(self.source,1)
        self.open_code=QPushButton("Open this code"); self.open_code.clicked.connect(lambda:self.codeRequested.emit(self.selected_sid) if self.selected_sid else None); info.addWidget(self.open_code)
        self.explain=QPushButton("Explain this path"); self.explain.clicked.connect(lambda:self.explainRequested.emit(self.selected_sid) if self.selected_sid else None); info.addWidget(self.explain)
        split.addWidget(detail); split.setSizes([780,295]); split.setStretchFactor(0,1); layout.addWidget(split,1)
        self.legend=QLabel("Potential impact →   Solid: resolved references   ·   Dashed: inferred / historical   ·   Click to follow a path; drag to explore")
        self.legend.setObjectName("muted"); self.legend.setWordWrap(True); layout.addWidget(self.legend)

    def eventFilter(self,watched,event):
        if watched is self.search and event.type()==QEvent.Type.KeyPress:
            if event.key()==Qt.Key.Key_Escape:self.search.clear();return True
            if event.key() in {Qt.Key.Key_Down,Qt.Key.Key_Up} and self.search_results.isVisible():
                direction=1 if event.key()==Qt.Key.Key_Down else -1
                self.search_results.setCurrentRow(max(0,min(self.search_results.count()-1,self.search_results.currentRow()+direction)));return True
        return super().eventFilter(watched,event)

    def search_components(self,query):
        self.search_results.clear();words=query.casefold().split()
        if not words or not self.snapshot:self.search_results.hide();self.search_count.clear();return
        matches=[(self.focus.itemText(i),self.focus.itemData(i)) for i in range(self.focus.count()) if self.focus.itemData(i)!=ALL_CHANGES and all(w in self.focus.itemText(i).casefold() for w in words)]
        query=query.strip().casefold()
        matches.sort(key=lambda item:(0 if item[1].split(':',1)[-1].casefold()==query else 1 if item[1].split(':',1)[-1].casefold().startswith(query) else 2 if all(w in item[1].split(':',1)[-1].casefold() for w in words) else 3,item[1]))
        for label,sid in matches[:100]:
            item=QListWidgetItem(label);item.setData(Qt.ItemDataRole.UserRole,sid);self.search_results.addItem(item)
        self.search_count.setText(f'{len(matches)} matches'+(' · first 100 shown' if len(matches)>100 else '') if matches else 'No matches')
        self.search_results.setVisible(bool(matches));self.search_results.setCurrentRow(0)

    def activate_search(self,*args):
        item=self.search_results.currentItem()
        if not item:return
        sid=item.data(Qt.ItemDataRole.UserRole);index=self.focus.findData(sid)
        if index>=0:self.focus.setCurrentIndex(index);self.focus_changed();self.inspect(sid)
        self.search_results.hide();self.search_count.setText('Focused');self.search.clearFocus()

    def set_tools_visible(self,show):
        for widget in (self.title,self.focus,self.trace,self.legend):widget.setVisible(show)
        self.mode.show();self.fit_button.show();self.summary.show()
        self.trace.hide()

    def change_projection(self,index):
        self.map_stack.setCurrentIndex(index)
        controls='Drag to orbit · right-drag to pan · scroll to zoom · Home resets' if index==2 else 'Drag to pan · scroll to zoom · Home resets' if index else 'Click to follow a path; drag to explore'
        self.legend.setText('Potential impact →   Solid: resolved references · Dashed: inferred / historical · '+controls)

    def fit_map(self):
        if self.mode.currentIndex()==2:self.perspective_map.reset_view()
        elif self.mode.currentIndex()==1:self.spatial_map.reset_view()
        else:self.map.fitInView(self.map.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)

    def spatial_selected(self,sid):
        self.map.select_node(sid)

    def set_report(self,snapshot,report):
        self.snapshot,self.report=snapshot,report
        previous=self.focus.currentData(); self.focus.clear()
        seeds=report["changes"]["seeds"]
        from .languages import language_for
        available=[sid for sid,s in snapshot.symbols.items() if
            (s.kind=="module" if language_for(s.path) in {"java","csharp","go","rust"} else not s.is_test and s.kind in {"function","async_function","class"})]
        choices=list(dict.fromkeys(seeds+available))
        if not choices:choices=[sid for sid,s in snapshot.symbols.items() if s.kind=="module"]
        if len(seeds)>1:self.focus.addItem(f'All changes · {len(seeds)} starting symbols',ALL_CHANGES)
        for sid in choices:self.focus.addItem((('Selected · ' if report.get('comparison')=='symbol' else 'Changed · ') if sid in seeds else '')+sid,sid)
        preferred=seeds[0] if seeds and report.get('comparison')=='symbol' else previous if not seeds or previous in seeds else ALL_CHANGES if len(seeds)>1 else seeds[0]
        index=self.focus.findData(preferred)
        if index>=0:self.focus.setCurrentIndex(index)
        self.trace.hide(); self.trace.setEnabled(bool(choices))
        self.show_root(self.focus.currentData())
        if self.search.text():self.search_components(self.search.text())

    def trace_current(self):
        if self.focus.currentData() and self.focus.currentData()!=ALL_CHANGES:self.traceRequested.emit(self.focus.currentData())

    def focus_changed(self,*args):self.show_root(self.focus.currentData())

    def show_root(self,root):
        # Recompute the focused path from indexed edges: a multi-seed report stores
        # only one shortest path per symbol and can otherwise hide shared callers.
        from .core import Snapshot, Symbol, impact_paths
        focused=self.report or {}
        if self.snapshot and root:
            history=focused.get("changes",{}).get("historical_symbols",{})
            merged=Snapshot(**{**self.snapshot.__dict__,"symbols":{**self.snapshot.symbols,**{sid:Symbol(**value) for sid,value in history.items()}},
                               "edges":self.snapshot.edges+focused.get("changes",{}).get("historical_edges",[])})
            roots=focused.get('changes',{}).get('seeds',[]) if root==ALL_CHANGES else [root]
            all_edges=merged.edges
            if not self.inferred.isChecked():merged.edges=[e for e in merged.edges if e['kind'] not in INFERRED]
            self.inferred_count=len(all_edges)-len(merged.edges)
            focused={**focused,"impact":impact_paths(merged,roots),'graph_edges':merged.edges}
        self.visible_edges=focused.get('graph_edges',[])
        rows,edges,hidden=map_records(focused,root)
        self.linked_tests={row["symbol"] for row in focused.get("impact",[]) if focused.get("locations",{}).get(row["symbol"],{}).get("is_test")}
        self.rows={row["symbol"]:row for row in rows}
        locations=(self.report or {}).get("locations",{})
        self.map.set_records(rows,edges,locations,root)
        self.spatial_map.set_records(rows,edges,locations,root)
        self.perspective_map.set_records(rows,edges,locations,root)
        tests=len(self.linked_tests)
        exploring=not self.report.get("changes",{}).get("seeds")
        self.title.setText("Function impact" if exploring else 'Project impact' if root==ALL_CHANGES else "Change impact")
        prefix="No edits yet · " if exploring else ""
        files=len({locations.get(row['symbol'],{}).get('path','') for row in rows})
        self.summary.setText(prefix+f"{len(rows)} shown symbols · {files} files · {tests} linked tests · click a node to follow its path"+(f" · {hidden} more in detailed evidence" if hidden else "") if rows else "No indexed source symbols. See Diagnostics for supported languages and parser issues.")
        self.focus.setToolTip(root or "")
        self.inspect(root if root in self.rows else None,False); self.detail.hide()
        if root in self.map.nodes:self.map.nodes[root].focused=True; self.map.nodes[root].update()
        self.focusUpdated.emit()

    def inspect(self,sid,reveal=True):
        if reveal and self.detail.isHidden():
            from .motion import reveal as show_drawer
            show_drawer(self.detail)
        self.selected_sid=sid; self.spatial_map.select_node(sid,emit=False);self.perspective_map.select_node(sid,emit=False); row=self.rows.get(sid)
        if not row:
            self.node_title.setText("Start with a function"); self.node_location.clear(); self.reason.setPlainText("Choose a function above and select Trace function. Saved edits will appear here automatically.")
            self.source.set_code(""); self.open_code.setEnabled(False); self.explain.setEnabled(False); return
        self.node_title.setText(sid.split(":",1)[-1]); location=self.report["locations"].get(sid,{})
        self.node_location.setText(f"{location.get('path','')} · lines {location.get('start','')}–{location.get('end','')}")
        evidence=row["evidence"]
        if evidence:
            steps=[]
            for edge in evidence:
                qualifier="inferred" if edge["kind"] in INFERRED else "resolved"
                steps.append(f"{edge['caller']}\n→ {edge['callee']}\nLine {edge['line']} · {edge['expression']} · {qualifier}")
            # A long path remains readable; the detailed evidence view retains every step.
            direct=[e for e in self.visible_edges if e['caller']==sid]
            references=[f"{e['caller']} → {e['callee']}\nLine {e['line']} · {e['expression']} · {'inferred' if e['kind'] in INFERRED else 'resolved static'}" for e in direct[:8]]
            self.reason.setPlainText('Recorded path from the focus:\n\n'+'\n\n'.join(steps[-3:])+('\nEarlier steps are in the detailed impact view.' if len(steps)>3 else '')+'\n\nThis node references:\n'+'\n\n'.join(references))
        else:self.reason.setPlainText("This is the changed or selected symbol where tracing starts. Connections indicate potential impact, not proof of a failure.")
        symbol=self.snapshot.symbols.get(sid)
        if symbol:self.source.set_language(symbol.path)
        self.source.set_code("".join(symbol.source.splitlines(True)[:12]) if symbol else "# This symbol was deleted.",symbol.start if symbol else 1)
        self.open_code.setEnabled(symbol is not None); self.explain.setEnabled(symbol is not None)
