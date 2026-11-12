"""Feature-first architecture browser with editable, source-linked flow cards."""
from copy import deepcopy
import sqlite3
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QLabel,QListWidget,QListWidgetItem,QSplitter,QPushButton,QTreeWidget,QTreeWidgetItem
from .design_canvas import EditableDesign
from .feature_flows import design_model,flow_entries


class FeatureFlows(QWidget):
    codeRequested=Signal(str,int)

    def __init__(self,parent=None):
        super().__init__(parent);self.report=None;self.cache={};self.key=None;self.bases={};self.visits=[];self.visit_index=-1;self.restoring=False;self.current_flow=None;self.detail=False;self.viewports={}
        col=QVBoxLayout(self);col.setContentsMargins(0,0,0,0);col.setSpacing(8)
        row=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('Find a feature, screen, endpoint or file…');self.search.setClearButtonEnabled(True);self.search.textChanged.connect(self.filter_flows);row.addWidget(self.search,1)
        home=QPushButton('System overview');home.clicked.connect(self.show_systems);row.addWidget(home);col.addLayout(row)
        self.summary=QLabel();self.summary.setWordWrap(True);self.summary.setObjectName('muted');col.addWidget(self.summary)
        self.journey=QLabel();self.journey.setWordWrap(True);self.journey.setTextFormat(Qt.TextFormat.PlainText);self.journey.setObjectName('muted');col.addWidget(self.journey)
        trail=QHBoxLayout();self.back=QPushButton('Back');self.forward=QPushButton('Forward');self.breadcrumb=QLabel('System overview');self.details=QPushButton('Implementation detail')
        self.back.clicked.connect(lambda:self.travel(-1));self.forward.clicked.connect(lambda:self.travel(1));self.details.clicked.connect(self.show_detail)
        for widget in (self.back,self.forward,self.breadcrumb,self.details):trail.addWidget(widget)
        col.addLayout(trail);self.results=QLabel();col.addWidget(self.results);self.update_trail()
        split=QSplitter(Qt.Orientation.Horizontal);self.features=QListWidget();self.features.setMinimumWidth(220);self.features.setMaximumWidth(360);self.features.setWordWrap(True);self.features.currentItemChanged.connect(self.open_feature);split.addWidget(self.features)
        self.canvas=EditableDesign();self.canvas.codeRequested.connect(self.codeRequested.emit);self.canvas.changed.connect(self.keep_draft);split.addWidget(self.canvas);split.setStretchFactor(1,1);split.setSizes([280,1100]);col.addWidget(split,1)
        self.coverage=QLabel();self.coverage.setWordWrap(True);self.coverage.setObjectName('muted');col.addWidget(self.coverage)
        self.evidence=QTreeWidget();self.evidence.setHeaderLabels(['Relationship','Classification','Source evidence']);self.evidence.setMinimumHeight(125);self.evidence.setMaximumHeight(180);self.evidence.setColumnWidth(0,150);self.evidence.setColumnWidth(1,160);self.evidence.hide();self.evidence.itemActivated.connect(lambda item,column:self.codeRequested.emit(*item.data(0,Qt.ItemDataRole.UserRole)) if item.data(0,Qt.ItemDataRole.UserRole) else None);col.addWidget(self.evidence)

    def set_report(self,report):
        previous=self.current_flow;detail=self.detail
        self.keep_draft();same=self.report and self.report.get('workspace_id',self.report['project'])==report.get('workspace_id',report['project'])
        if not same:self.visits=[];self.visit_index=-1;previous=None
        self.report=report;self.key=None
        self.by_id={f['id']:f for f in flow_entries(report.get('feature_flows',{}))}
        data=report.get('feature_flows',{});s=data.get('summary',{})
        self.summary.setText(f"{s.get('requests',0)} HTTP requests · {s.get('server_routes',0)} registered routes · {s.get('path_matches',0)} unique local path matches · {s.get('ambiguous',0)} ambiguous · {s.get('unresolved',0)} unlinked · {s.get('skipped_files',0)} files skipped by flow parser")
        self.coverage.setText('Module overview covers every indexed language. HTTP adapters: Express, Next App Router, direct FastAPI/Flask routes. Hosts, runtime wiring and unsupported framework flows remain unverified.')
        self.filter_flows()
        if previous in self.by_id:self.open_flow(self.by_id[previous],detail)
        else:self.show_systems()

    def filter_flows(self,*args):
        self.features.blockSignals(True);self.features.clear()
        words=self.search.text().casefold().split()
        for flow in sorted(flow_entries((self.report or {}).get('feature_flows',{})),key=lambda f:(f['app'],f.get('screen',''),f['title'])):
            label=flow['app']+' / '+flow.get('screen','')+' / '+flow['title']
            searchable=label+' '+flow['path']+' '+' '.join(str(s['label'])+' '+str(s['source']['path']) for s in flow.get('steps',[]))
            if not all(word in searchable.casefold() for word in words):continue
            status={'path match':'Path candidate','unresolved':'Unlinked','ambiguous':'Ambiguous','registered':'Registered route'}[flow['status']]
            item=QListWidgetItem(label+'\n'+status+' · '+flow['path']+':'+str(flow['line']));item.setData(Qt.ItemDataRole.UserRole,flow['id']);item.setToolTip(label);self.features.addItem(item)
        self.features.blockSignals(False);self.results.setText(str(self.features.count())+' matching entries · grouped by application / screen')
        if words and not self.features.count():self.coverage.setText('No matching extracted features. Search matches screen names, URLs and source paths. Unsupported requests may be absent; use Code structure to inspect source.')

    def keep_draft(self):
        if self.key and self.canvas.model:
            self.cache[self.key]=deepcopy(self.canvas.model)
            self.viewports[self.key]=(self.canvas.view.transform(),self.canvas.view.horizontalScrollBar().value(),self.canvas.view.verticalScrollBar().value())
            base=self.bases.get(self.key)
            if base:
                from .flow_drafts import draft_store
                try:draft_store(*self.key,base,self.canvas.model)
                except (OSError,sqlite3.Error,ValueError,KeyError,TypeError) as exc:self.coverage.setText('Draft remains in memory; could not save annotations: '+str(exc))

    def show_model(self,flow=None):
        if not self.report:return
        self.keep_draft();self.key=(self.report.get('workspace_id',self.report['project']),flow['id'] if flow else 'systems')
        fresh=design_model(self.report,flow);draft=self.cache.get(self.key)
        if draft is None:
            from .flow_drafts import draft_store
            try:saved=draft_store(*self.key)
            except (OSError,sqlite3.Error,ValueError,KeyError,TypeError):saved=None
            if saved:draft=saved['draft'];self.bases[self.key]=saved['base']
        if draft and draft['snapshot_id']!=fresh['snapshot_id']:
            from .flow_drafts import rebase_draft
            draft=rebase_draft(self.bases.get(self.key,draft),draft,fresh)
        self.bases[self.key]=deepcopy(fresh)
        self.canvas.expected_snapshot=self.report['snapshot_id'];self.canvas.set_model(draft or fresh)
        viewport=self.viewports.get(self.key)
        if viewport:
            self.canvas.view.setTransform(viewport[0]);self.canvas.view.horizontalScrollBar().setValue(viewport[1]);self.canvas.view.verticalScrollBar().setValue(viewport[2])
        else:QTimer.singleShot(0,self.canvas.frame_readable)

    def update_trail(self):
        self.back.setEnabled(self.visit_index>0);self.forward.setEnabled(self.visit_index+1<len(self.visits));self.details.setEnabled(self.current_flow is not None)
        flow=getattr(self,'by_id',{}).get(self.current_flow)
        self.breadcrumb.setText('System overview'+(' → '+flow.get('screen',flow['title']) if flow else '')+(' → Implementation detail' if self.detail else ''))

    def display(self,flow=None,detail=False):
        self.current_flow=flow['id'] if flow else None;self.detail=detail
        state=(self.current_flow,detail)
        if not self.restoring and (self.visit_index<0 or self.visits[self.visit_index]!=state):
            self.visits=self.visits[:self.visit_index+1]+[state];self.visit_index=len(self.visits)-1
        self.show_model(flow);self.update_trail()
        self.evidence.clear();self.evidence.setVisible(bool(flow and detail))
        if flow and detail:
            for relation in flow.get('relationships',[]):
                for ev in relation['evidence']:
                    row=QTreeWidgetItem(self.evidence,[relation['kind'],relation['classification'],str(ev['path'])+':'+str(ev['line'])+' · '+ev['description']]);row.setData(0,Qt.ItemDataRole.UserRole,(ev['path'],ev['line']))
        if flow and detail:self.journey.setText(self.journey.text()+' Select a card to inspect its source evidence and editable annotations.')

    def travel(self,direction):
        index=self.visit_index+direction
        if not 0<=index<len(self.visits):return
        self.visit_index=index;key,detail=self.visits[index];self.restoring=True
        try:
            if key in self.by_id:self.open_flow(self.by_id[key],detail)
            else:self.show_systems()
        finally:self.restoring=False

    def show_detail(self):
        flow=self.by_id.get(self.current_flow)
        if flow:self.open_flow(flow,True)

    def show_systems(self):
        self.journey.setText('Explore the indexed source modules, dependencies and registered routes below. Choose a request to inspect a supported feature path. Code structure contains declaration details for every indexed language.')
        self.features.blockSignals(True);self.features.clearSelection();self.features.setCurrentRow(-1);self.features.blockSignals(False);self.display()

    def open_feature(self,item,previous=None):
        if item is None:return
        flow=self.by_id.get(item.data(Qt.ItemDataRole.UserRole))
        if flow:self.open_flow(flow)

    def open_flow(self,flow,detail=False):
        if flow:
            self.features.blockSignals(True)
            for row in range(self.features.count()):
                if self.features.item(row).data(Qt.ItemDataRole.UserRole)==flow['id']:self.features.setCurrentRow(row);break
            self.features.blockSignals(False)
            self.display(flow,detail);self.coverage.setText(' · '.join([flow['origin']]+flow.get('gaps',flow['notes'])) or 'Source-linked implementation flow. Branches are alternatives; no repository code was executed.')
            parts=['Source registers '+flow['method']+' '+flow['url']+'.' if flow.get('entry_kind')=='server' else (flow['owners'][-1][0] if flow['owners'] else 'The client')+' sends '+flow['method']+' '+flow['url']+'.']
            if len(flow['matches'])==1:
                handler=flow['matches'][0]['handler_detail']
                if handler:
                    parts.append('A compatible local route registers '+handler['name']+'.')
                    if handler['data']:parts.append('Its source uses '+', '.join(v['operation'] for v in handler['data'][:3])+'.')
                    services=flow['matches'][0].get('service_helpers',[])
                    if services:
                        parts.append('It calls local services '+', '.join(h['name'] for h in services[:4])+'.')
                        operations=[d['operation'] for h in services for d in h['data']]
                        if operations:parts.append('Those services reference '+', '.join(operations[:4])+'.')
                    if handler['responses']:parts.append('Possible responses: '+', '.join('HTTP '+r['status']+' ['+', '.join(r['fields'])+']' for r in handler['responses'][:3])+'.')
            if flow['updates']:
                parts.append('The client assigns returned data to '+', '.join(u['state'] for u in flow['updates'])+'.')
                if any(u['renders'] for u in flow['updates']):parts.append('That state is used in list rendering.')
            else:parts.append('The connection from returned data to UI state was not resolved.')
            if flow.get('gaps'):parts.append(str(len(flow['gaps']))+' unresolved steps are listed below.')
            self.journey.setText(' '.join(parts))
