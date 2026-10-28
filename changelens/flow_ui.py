"""Feature-first architecture browser with editable, source-linked flow cards."""
from copy import deepcopy
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QLabel,QListWidget,QListWidgetItem,QSplitter,QPushButton
from .design_canvas import EditableDesign
from .feature_flows import design_model


class FeatureFlows(QWidget):
    codeRequested=Signal(str,int)

    def __init__(self,parent=None):
        super().__init__(parent);self.report=None;self.cache={};self.key=None
        col=QVBoxLayout(self);col.setContentsMargins(0,0,0,0);col.setSpacing(8)
        row=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('Find a feature, screen, endpoint or file…');self.search.setClearButtonEnabled(True);self.search.textChanged.connect(self.filter_flows);row.addWidget(self.search,1)
        home=QPushButton('System overview');home.clicked.connect(self.show_systems);row.addWidget(home);col.addLayout(row)
        self.summary=QLabel();self.summary.setWordWrap(True);self.summary.setObjectName('muted');col.addWidget(self.summary)
        self.journey=QLabel();self.journey.setWordWrap(True);self.journey.setTextFormat(Qt.TextFormat.PlainText);self.journey.setObjectName('muted');col.addWidget(self.journey)
        split=QSplitter(Qt.Orientation.Horizontal);self.features=QListWidget();self.features.setMinimumWidth(220);self.features.setMaximumWidth(360);self.features.setWordWrap(True);self.features.currentItemChanged.connect(self.open_feature);split.addWidget(self.features)
        self.canvas=EditableDesign();self.canvas.codeRequested.connect(self.codeRequested.emit);self.canvas.changed.connect(self.keep_draft);split.addWidget(self.canvas);split.setStretchFactor(1,1);split.setSizes([280,1100]);col.addWidget(split,1)
        self.coverage=QLabel();self.coverage.setWordWrap(True);self.coverage.setObjectName('muted');col.addWidget(self.coverage)

    def set_report(self,report):
        self.keep_draft();self.report=report;self.key=None
        data=report.get('feature_flows',{});s=data.get('summary',{})
        self.summary.setText(f"{s.get('requests',0)} HTTP requests · {s.get('path_matches',0)} unique local path matches · {s.get('ambiguous',0)} ambiguous · {s.get('unresolved',0)} unlinked · {s.get('skipped_files',0)} files skipped by flow parser")
        self.coverage.setText('Static React/Axios/fetch → Express support. Host / proxy and runtime behavior are unverified. Click a feature, then a card for source and editable details.')
        self.filter_flows();self.show_systems()

    def filter_flows(self,*args):
        self.features.blockSignals(True);self.features.clear()
        words=self.search.text().casefold().split()
        for flow in (self.report or {}).get('feature_flows',{}).get('flows',[]):
            label=flow['app']+' / '+flow['title']
            if not all(word in (label+' '+flow['path']).casefold() for word in words):continue
            status={'path match':'Path candidate','unresolved':'Unlinked','ambiguous':'Ambiguous'}[flow['status']]
            item=QListWidgetItem(label+'\n'+status+' · '+flow['path']+':'+str(flow['line']));item.setData(Qt.ItemDataRole.UserRole,flow['id']);item.setToolTip(label);self.features.addItem(item)
        self.features.blockSignals(False)
        if words and not self.features.count():self.coverage.setText('No matching extracted features. Search matches screen names, URLs and source paths. Unsupported requests may be absent; use Code structure to inspect source.')

    def keep_draft(self):
        if self.key and self.canvas.model:self.cache[self.key]=deepcopy(self.canvas.model)

    def show_model(self,flow=None):
        if not self.report:return
        self.keep_draft();self.key=(self.report['snapshot_id'],flow['id'] if flow else 'systems')
        self.canvas.expected_snapshot=self.report['snapshot_id'];self.canvas.set_model(self.cache.get(self.key) or design_model(self.report,flow))
        QTimer.singleShot(0,self.canvas.frame_readable)

    def show_systems(self):
        self.journey.setText('Start with the applications and server boundaries below. Choose a feature on the left to inspect its request, server logic, response branches and UI updates. Code structure remains a separate view.')
        self.features.blockSignals(True);self.features.clearSelection();self.features.setCurrentRow(-1);self.features.blockSignals(False);self.show_model()

    def open_feature(self,item,previous=None):
        if item is None:return
        flow=next((f for f in self.report['feature_flows']['flows'] if f['id']==item.data(Qt.ItemDataRole.UserRole)),None)
        if flow:
            self.show_model(flow);self.coverage.setText(' · '.join([flow['origin']]+flow['notes']) or 'Source-linked implementation flow. Branches are alternatives; no repository code was executed.')
            parts=[(flow['owners'][-1][0] if flow['owners'] else 'The client')+' sends '+flow['method']+' '+flow['url']+'.']
            if len(flow['matches'])==1:
                handler=flow['matches'][0]['handler_detail']
                if handler:
                    parts.append('A compatible local route registers '+handler['name']+'.')
                    if handler['data']:parts.append('Its source uses '+', '.join(v['operation'] for v in handler['data'][:3])+'.')
                    if handler['responses']:parts.append('Possible responses: '+', '.join('HTTP '+r['status']+' ['+', '.join(r['fields'])+']' for r in handler['responses'][:3])+'.')
            if flow['updates']:
                parts.append('The client assigns returned data to '+', '.join(u['state'] for u in flow['updates'])+'.')
                if any(u['renders'] for u in flow['updates']):parts.append('That state is used in list rendering.')
            else:parts.append('The connection from returned data to UI state was not resolved.')
            self.journey.setText(' '.join(parts))
