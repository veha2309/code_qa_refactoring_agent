"""Offline architecture review, declaration browser and standalone SVG previews."""
from pathlib import Path
from PySide6.QtCore import Qt, QByteArray, Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTabWidget,QTreeWidget,QTreeWidgetItem,QHeaderView,QScrollArea,QComboBox,QCheckBox,QLineEdit,QSplitter
from PySide6.QtSvgWidgets import QSvgWidget
from .brief import BriefView
from .architecture import diagram_svg, md_text


class ArchitectureView(QWidget):
    generateRequested=Signal()
    exportRequested=Signal()
    codeRequested=Signal(str,int)

    def __init__(self,parent=None):
        super().__init__(parent);self.report=None
        col=QVBoxLayout(self);col.setContentsMargins(0,0,0,0);col.setSpacing(12)
        row=QHBoxLayout();title=QLabel('Architecture');title.setObjectName('lensTitle');self.heading_title=title;row.addWidget(title,1)
        self.generate=QPushButton('Review project');self.generate.clicked.connect(self.generateRequested.emit);row.addWidget(self.generate)
        self.export=QPushButton('Export report + diagrams');self.export.setEnabled(False);self.export.clicked.connect(self.exportRequested.emit);row.addWidget(self.export);col.addLayout(row)
        self.status=QLabel('Open a project, then review its saved source. No project code will be executed.');self.status.setWordWrap(True);self.status.setObjectName('muted');col.addWidget(self.status)
        self.tabs=QTabWidget();col.addWidget(self.tabs,1)
        review_page=QSplitter(Qt.Orientation.Vertical)
        self.overview=BriefView();self.overview.setPlainText('## Project review\n\nReview source-backed dependency paths, coverage gaps and extracted feature flows.');review_page.addWidget(self.overview)
        self.review_items=QTreeWidget();self.review_items.setHeaderLabels(['Review / source location','Evidence and interpretation','Next step']);self.review_items.setColumnWidth(0,380);self.review_items.setColumnWidth(1,500);self.review_items.header().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch);self.review_items.setWordWrap(True);self.review_items.itemActivated.connect(self.open_review_item);self.review_items.currentItemChanged.connect(self.describe_review_item);review_page.addWidget(self.review_items);review_page.setSizes([210,650]);self.tabs.addTab(review_page,'Review')
        self.declarations=QTreeWidget();self.declarations.setHeaderLabels(['Declaration','Kind','Source','Signature / excerpt'])
        self.declarations.setColumnWidth(0,240);self.declarations.setColumnWidth(1,100);self.declarations.setColumnWidth(2,260);self.declarations.header().setSectionResizeMode(3,QHeaderView.ResizeMode.Stretch)
        self.declarations.itemActivated.connect(self.open_item);self.tabs.addTab(self.declarations,'Code inventory')
        self.dependencies=QTreeWidget();self.dependencies.setHeaderLabels(['Caller file → dependency','Evidence / classification']);self.dependencies.setColumnWidth(0,540);self.dependencies.header().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        self.dependencies.itemActivated.connect(self.open_item);self.tabs.addTab(self.dependencies,'Dependencies')
        diagram=QWidget();dc=QVBoxLayout(diagram);dc.setContentsMargins(0,0,0,0)
        self.diagram_controls=QWidget();controls=QHBoxLayout(self.diagram_controls);controls.setContentsMargins(0,0,0,0)
        self.diagram_choice=QComboBox();self.diagram_choice.addItems(['Package dependencies','Declarations & members']);self.diagram_choice.currentIndexChanged.connect(self.configure_diagrams);controls.addWidget(self.diagram_choice)
        self.scope=QComboBox();self.scope.setMinimumWidth(230);self.scope.currentIndexChanged.connect(self.configure_pages);controls.addWidget(self.scope,1)
        self.diagram_page=QComboBox();self.diagram_page.currentIndexChanged.connect(self.update_diagram);controls.addWidget(self.diagram_page)
        self.include_aux=QCheckBox('Tests / generated');self.include_aux.toggled.connect(self.configure_diagrams);controls.addWidget(self.include_aux)
        for name,callback in [('−',lambda:self.scale_diagram(.8)),('+',lambda:self.scale_diagram(1.25)),('Fit',self.fit_diagram)]:
            button=QPushButton(name);button.clicked.connect(callback);controls.addWidget(button)
        dc.addWidget(self.diagram_controls)
        self.diagram_note=QLabel('Select a package for a readable member-level design. Export includes every package and page.');self.diagram_note.setObjectName('muted');self.diagram_note.setWordWrap(True);dc.addWidget(self.diagram_note)
        self.diagram=QSvgWidget();self.diagram_scroll=QScrollArea();self.diagram_scroll.setWidget(self.diagram);self.diagram_scroll.setWidgetResizable(False);self.diagram_scroll.viewport().setStyleSheet("background:#171d25;");self.diagram_scroll.hide()
        from .design_canvas import EditableDesign
        self.canvas=EditableDesign();self.canvas.codeRequested.connect(self.codeRequested.emit);self.canvas.changed.connect(self.cache_design);self.design_cache={};self.design_key=None;dc.addWidget(self.canvas,1);self.tabs.addTab(diagram,'Code structure')
        from .flow_ui import FeatureFlows
        self.flows=FeatureFlows();self.flows.codeRequested.connect(self.codeRequested.emit);self.tabs.addTab(self.flows,'System & feature flows')
        coverage=QWidget();cv=QVBoxLayout(coverage);cv.setContentsMargins(0,0,0,0)
        self.coverage_summary=QLabel();self.coverage_summary.setWordWrap(True);cv.addWidget(self.coverage_summary)
        filters=QHBoxLayout();self.coverage_query=QLineEdit();self.coverage_query.setPlaceholderText('Find a file, reference or diagnostic text…');self.coverage_query.textChanged.connect(self.populate_coverage);filters.addWidget(self.coverage_query,1)
        self.coverage_kind=QComboBox();self.coverage_kind.currentIndexChanged.connect(self.populate_coverage);filters.addWidget(self.coverage_kind);cv.addLayout(filters)
        self.coverage_rows=QTreeWidget();self.coverage_rows.setHeaderLabels(['Analysis coverage','Occurrences / files','Examples · source locations']);self.coverage_rows.setColumnWidth(0,410);self.coverage_rows.setColumnWidth(1,170);self.coverage_rows.header().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch);self.coverage_rows.itemActivated.connect(self.open_item);cv.addWidget(self.coverage_rows,1);self.tabs.addTab(coverage,'Analysis coverage')
        self.diagram_zoom=1.
        self.tabs.setCurrentIndex(3)

    def set_tools_visible(self,show):
        for widget in (self.heading_title,self.generate,self.export,self.status,self.diagram_note,self.canvas.notice):widget.setVisible(show)
        self.diagram_controls.show();self.canvas.toolbar.show();self.tabs.tabBar().show()
        if not self.canvas.scene.selectedItems():self.canvas.inspector.hide()

    def active_canvas(self):return self.flows.canvas if self.tabs.currentWidget() is self.flows else self.canvas

    def reset_active_design(self):
        if self.tabs.currentWidget() is not self.flows:self.reset_design();return
        if not self.report:return
        from .feature_flows import design_model
        key=self.flows.key[1] if self.flows.key else 'systems'
        flow=next((f for f in self.report.get('feature_flows',{}).get('flows',[]) if f['id']==key),None)
        model=design_model(self.report,flow)
        self.flows.canvas.transaction('Reset flow to source',lambda value:(value.clear(),value.update(model)))

    def clear_report(self):
        self.report=None;self.export.setEnabled(False);self.declarations.clear();self.dependencies.clear();self.design_key=None;self.canvas.set_model(None);self.canvas.expected_snapshot=''
        self.diagram.load(QByteArray(b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>'))
        self.overview.setPlainText('## Architecture and implementation LLD\n\nOpen this view to review the current project, or choose Review project to refresh saved-source evidence.')
        self.status.setText('No architecture report for the current project yet.')
        self.flows.report=None;self.flows.key=None;self.flows.features.clear();self.flows.canvas.set_model(None)
        self.review_items.clear();self.coverage_rows.clear();self.coverage_summary.clear()

    def open_item(self,item,column=0):
        data=item.data(0,Qt.ItemDataRole.UserRole)
        if data:self.codeRequested.emit(data[0],data[1])

    def set_report(self,report):
        from .design_diagrams import prepare_diagrams
        report=prepare_diagrams(report)
        self.report=report;self.export.setEnabled(True);summary=report['summary']
        self.status.setText(f"{summary['files']} files · {summary['classes']} classes · {summary['relationships']} relationships · snapshot {report['snapshot_id']} · saved source only")
        self.populate_review();self.declarations.clear();items={}
        pending=sorted((s for s in report['symbols'] if s['kind']!='module'),key=lambda s:(s['path'],s['qualname'].count('.'),s['start']))
        for s in pending[:2000]:
            parent=items.get(s['owner'],self.declarations)
            item=QTreeWidgetItem(parent,[s['qualname'],s['kind'],f"{s['path']}:{s['start']}–{s['end']}",s['signature'] or s['header']]);items[s['id']]=item
            item.setData(0,Qt.ItemDataRole.UserRole,(s['path'],s['start']));item.setToolTip(3,s['signature'] or s['header'])
            for field in s['fields']:
                child=QTreeWidgetItem(item,[field['name'],'field','',field['annotation']]);child.setData(0,Qt.ItemDataRole.UserRole,(s['path'],s['start']))
            for base in s['bases']:QTreeWidgetItem(item,[base,'declared base','','Type resolution not performed'])
        self.dependencies.clear()
        for edge in report['dependencies'][:500]:
            item=QTreeWidgetItem(self.dependencies,[edge['from']+' → '+edge['to'],f"{edge['classification']} · {len(edge['evidence'])} evidence records"])
            item.setData(0,Qt.ItemDataRole.UserRole,(edge['from'],1))
            for ev in edge['evidence'][:30]:
                child=QTreeWidgetItem(item,[f"{ev['caller']} → {ev['callee']}",f"line {ev['line']} · {ev['kind']} · {ev['expression']}"])
                child.setData(0,Qt.ItemDataRole.UserRole,(ev['path'],ev['line']))
            if len(edge['evidence'])>30:QTreeWidgetItem(item,['Additional evidence',f"{len(edge['evidence'])-30} more records in report.json"])
        if len(pending)>2000 or len(report['dependencies'])>500:
            self.status.setText(self.status.text()+' · Preview capped at 2,000 declarations / 500 dependencies; export contains all records')
        self.configure_diagrams()
        self.flows.set_report(report)
        if report.get('feature_flows',{}).get('flows'):self.tabs.setCurrentWidget(self.flows)

    def populate_review(self):
        from .review_quality import build_review
        report=self.report;review=report.get('review') or build_review(report);report['review']=review;digest=review['coverage'];counts=digest['counts']
        lines=['## '+md_text(report['project'])+' · project review','',
            f"{len(review['items'])} grouped review items · {counts.get('parser exclusions',0)} parser exclusions · {counts.get('unresolved local imports',0)} unresolved local code imports",'',
            'Select an item for its full explanation and next step. Expand it and double-click a source row to inspect the recorded reference.','',
            f"{review['metrics']['large_definitions']} long definitions and {review['metrics']['coupled_files']} high fan-out files are inventory metrics, not separate defect claims. Dynamic / external references are grouped in Analysis coverage. No runtime behavior was verified."]
        self.overview.setPlainText('\n'.join(lines));self.review_items.clear()
        if review['systems']:
            systems=QTreeWidgetItem(self.review_items,['Extracted system boundaries','Manifest roles and HTTP request evidence','Open an example feature to inspect its implementation path'])
            for system in review['systems']:
                row=QTreeWidgetItem(systems,[system['name'],f"{system['requests']} requests · {system['unique_path_candidates']} unique local path candidates · {system['unlinked']} unlinked",system['example_title']]);row.setData(0,Qt.ItemDataRole.UserRole,('feature',system['example_id']))
            systems.setExpanded(True)
        for entry in review['items']:
            row=QTreeWidgetItem(self.review_items,[entry['priority']+' · '+entry['title'],entry['explanation'],entry['next_step']])
            row.setData(0,Qt.ItemDataRole.UserRole+1,entry)
            for ev in entry['evidence'][:30]:
                source=ev.get('path','');line=ev.get('line',1)
                child=QTreeWidgetItem(row,[source+':'+str(line),ev.get('expression') or ev.get('message',''),'Open this recorded source reference'])
                if source:child.setData(0,Qt.ItemDataRole.UserRole,(source,line))
            if len(entry['evidence'])>30:QTreeWidgetItem(row,['More source evidence',f"{len(entry['evidence'])-30} additional anchors retained in report.json",''])
        self.coverage_kind.blockSignals(True);self.coverage_kind.clear();self.coverage_kind.addItem('All coverage categories','')
        for category,count in counts.items():self.coverage_kind.addItem(category+' · '+str(count),category)
        self.coverage_kind.blockSignals(False);self.populate_coverage()

    def describe_review_item(self,item,previous=None):
        if item is None:return
        current=item;entry=None
        while current is not None and entry is None:
            entry=current.data(0,Qt.ItemDataRole.UserRole+1);current=current.parent()
        if not entry:return
        lines=['## '+md_text(entry['title']),'',md_text(entry['explanation']),'','**Next step:** '+md_text(entry['next_step']),'']
        for evidence in entry['evidence'][:5]:lines+=['- `'+md_text(evidence['path'])+':'+str(evidence.get('line',1))+'` · '+md_text(evidence.get('expression') or evidence.get('message',''))]
        self.overview.setPlainText('\n'.join(lines))

    def open_review_item(self,item,column=0):
        value=item.data(0,Qt.ItemDataRole.UserRole)
        if not value:return
        if value[0]=='feature':
            self.tabs.setCurrentWidget(self.flows);self.flows.search.clear()
            for i in range(self.flows.features.count()):
                if self.flows.features.item(i).data(Qt.ItemDataRole.UserRole)==value[1]:self.flows.features.setCurrentRow(i);break
        else:self.open_item(item,column)

    def populate_coverage(self,*args):
        if not self.report:return
        digest=self.report.get('review',{}).get('coverage',{});query=self.coverage_query.text().casefold();category=self.coverage_kind.currentData();self.coverage_rows.clear()
        if query:
            from .review_quality import diagnostic_digest
            groups=diagnostic_digest([w for w in self.report['warnings'] if query in w.casefold()])['groups']
        else:groups=digest.get('groups',[])
        rows=[g for g in groups if not category or g['category']==category]
        for group in rows[:500]:
            item=QTreeWidgetItem(self.coverage_rows,[group['category']+' · '+group['title'],f"{group['count']} / {group['file_count']} files",group['examples'][0]['message'] if group['examples'] else ''])
            for example in group['examples']:
                child=QTreeWidgetItem(item,[example['path']+':'+str(example['line']),'Example',example['message']])
                if example['path']:child.setData(0,Qt.ItemDataRole.UserRole,(example['path'],example['line']))
        self.coverage_summary.setText(f"{digest.get('raw_occurrences',0)} raw diagnostic occurrences → {len(digest.get('groups',[]))} groups · {len(rows)} match this filter · {min(500,len(rows))} shown. Unresolved references describe analyzer limits; they are not code-error counts. Full occurrences remain in report.json.")

    def configure_diagrams(self,*args):
        if not self.report:return
        from .design_diagrams import scopes,candidates
        previous=self.scope.currentData();self.scope.blockSignals(True);self.scope.clear();
        if self.diagram_choice.currentIndex()==0:self.scope.addItem('Project overview',None)
        for scope in scopes(self.report,self.include_aux.isChecked()):
            self.scope.addItem(f'{scope} · {len(candidates(self.report,scope,self.include_aux.isChecked()))} items',scope)
        index=self.scope.findData(previous)
        if index<0 and self.diagram_choice.currentIndex()==1:index=self.scope.findData('lib/app')
        if index>=0:self.scope.setCurrentIndex(index)
        self.scope.blockSignals(False);self.scope.setVisible(self.diagram_choice.currentIndex()==1)
        self.configure_pages()

    def configure_pages(self,*args):
        if not self.report:return
        from .design_diagrams import page_count
        scope=self.scope.currentData() if self.diagram_choice.currentIndex()==1 else None
        count=page_count(self.report,scope,self.include_aux.isChecked());self.diagram_page.blockSignals(True);self.diagram_page.clear()
        for i in range(count):self.diagram_page.addItem(f'Page {i+1} / {count}',i)
        self.diagram_page.blockSignals(False);self.update_diagram()

    def update_diagram(self,*args):
        if not self.report:return
        scope=self.scope.currentData() if self.diagram_choice.currentIndex()==1 else None
        svg=diagram_svg(self.report,self.diagram_choice.currentIndex()==1,scope=scope,page=max(0,self.diagram_page.currentIndex()),include_aux=self.include_aux.isChecked())
        self.diagram.load(QByteArray(svg.encode('utf-8')));self.natural_diagram_size=self.diagram.renderer().defaultSize();self.fit_diagram()
        self.diagram_note.setText(('Code structure: fields, constructors and method signatures in this scope. ' if scope else 'Code structure: package dependencies. ')+'For system behavior and request / response details, open System & feature flows. Move cards or edit a saved design draft; these changes do not edit source.')

        from .design_canvas import extracted_model
        key=(self.report['snapshot_id'],'LLD' if scope else 'HLD',scope,max(0,self.diagram_page.currentIndex()),self.include_aux.isChecked())
        self.design_key=key
        model=self.design_cache.get(key)
        if model is None:
            from .design_canvas import validate_model
            import json
            recovery=self.design_recovery_path(key)
            try:
                if recovery.exists() and recovery.stat().st_size<10_000_000:
                    model=json.loads(recovery.read_text(encoding='utf-8'));validate_model(model)
            except (OSError,ValueError,KeyError,TypeError):model=None
        model=model or extracted_model(self.report,key[1],scope,key[3],key[4])
        self.canvas.expected_snapshot=self.report['snapshot_id'];self.canvas.set_model(model)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0,self.canvas.frame_readable)

    def cache_design(self):
        if self.design_key and self.canvas.model:
            from copy import deepcopy
            self.design_cache[self.design_key]=deepcopy(self.canvas.model)
            try:
                import json
                from PySide6.QtCore import QSaveFile,QIODevice
                path=self.design_recovery_path(self.design_key);path.parent.mkdir(parents=True,exist_ok=True)
                saved=QSaveFile(str(path))
                if not saved.open(QIODevice.OpenModeFlag.WriteOnly):raise OSError(saved.errorString())
                raw=json.dumps(self.canvas.model,ensure_ascii=False).encode('utf-8')
                if saved.write(raw)!=len(raw) or not saved.commit():raise OSError(saved.errorString())
            except OSError as exc:self.canvas.notice.setText('Recovery save failed; use Save design to keep this draft. '+str(exc));self.canvas.notice.show()

    def reset_design(self):
        if not self.report or not self.design_key:return
        from .design_canvas import extracted_model
        key=self.design_key;fresh=extracted_model(self.report,key[1],key[2],key[3],key[4])
        def reset(model):model.clear();model.update(fresh)
        self.canvas.transaction('Reset page to extracted source',reset)

    def design_recovery_path(self,key):
        import hashlib,json
        from .core import app_dir
        identity=hashlib.sha256(json.dumps(key,ensure_ascii=False).encode('utf-8')).hexdigest()
        return app_dir()/'design-drafts'/(identity+'.json')

    def fit_diagram(self):
        if hasattr(self,'canvas'):self.canvas.fit()
        if not hasattr(self,'natural_diagram_size'):return
        self.diagram_zoom=min(1.,max(.2,(self.diagram_scroll.viewport().width()-20)/max(1,self.natural_diagram_size.width())))
        self.scale_diagram(1.)

    def scale_diagram(self,factor):
        if hasattr(self,'canvas'):self.canvas.view.scale(factor,factor)
        if not hasattr(self,'natural_diagram_size'):return
        self.diagram_zoom=max(.2,min(2.5,self.diagram_zoom*factor));self.diagram.setFixedSize(self.natural_diagram_size*self.diagram_zoom)
