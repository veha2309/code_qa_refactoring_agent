"""Native code workbench. Editing, review and analysis are separate workflows."""
from pathlib import Path
from threading import Event
import json
import os
import sys

from PySide6.QtCore import Qt, QSize, QTimer, QFileSystemWatcher
from PySide6.QtGui import QAction, QFont, QFontDatabase, QIcon, QKeySequence, QTextCursor
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSpinBox, QSplitter,
    QStackedWidget, QTabWidget, QTableWidget, QTableWidgetItem, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget, QAbstractItemView, QSizePolicy)

from .jobs import Worker
from .core import EXCLUDED, app_dir, checkpoint, decode_source, ensure_fresh, git, index_repository, report_markdown
from .workspace import Document, analyze_workspace, capture_baseline, load_baseline
from .ranking import resources, train_model
from .completion import complete_python, find_definition
from .refactoring import apply_reviewed_patch, preview_refactoring, suggestions
from .runner import detect_interpreter, run_project_tests
from .demo import execute_demo
from .widgets import CodeEditor, DiffViewer, icon
from .theme import STYLESHEET
from .ai_workbench import AIWorkbench
from .lens import ChangeLens
from .languages import is_source,is_indexable,language_for,NAMES
from .polyglot import INFERRED_KINDS
from .js_runner import execution_family,detect_node
from .formatting import formatter_for,format_document
from .format_ui import FormatPreview,apply_to_editor
from .surfaces import GlassWorkspace
from .motion import AnimatedStack,AnimatedNavigation,atomic_paint,paint_transaction


def text(value, style=""):
    widget=QLabel(value); widget.setWordWrap(True); widget.setObjectName(style)
    widget.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Maximum)
    return widget


def action(value, callback, primary=False, glyph=None):
    widget=QPushButton(value); widget.clicked.connect(callback)
    widget.setObjectName("primary" if primary else "button")
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if glyph: widget.setIcon(icon(glyph,"#a0a0a0"))
    return widget


def column(widget=None, margins=0):
    widget=widget or QWidget(); layout=QVBoxLayout(widget); layout.setContentsMargins(margins,margins,margins,margins); layout.setSpacing(12)
    return widget,layout


class MainWindow(AIWorkbench,QMainWindow):
    def __init__(self):
        super().__init__()
        for name in ("NotoSans-Regular.ttf","NotoSansMono-Regular.ttf","RobotoMono.ttf"):
            QFontDatabase.addApplicationFont(str(resources()/"fonts"/name))
        self.snapshot=self.report=self.patch=self.worker=self.completion_worker=None
        self._pending_result=self._pending_error=None
        self.documents={}; self.editors={}; self.change_rows=[]; self.test_rows=[]; self.trusted_roots=set()
        self.report_stale=False; self.patch_stale=False; self.test_choices={}
        self.pending_check=False; self.auto_refresh=False
        self.check_timer=QTimer(self); self.check_timer.setSingleShot(True); self.check_timer.setInterval(1000); self.check_timer.timeout.connect(self.automatic_check)
        self.preview_timer=QTimer(self); self.preview_timer.setSingleShot(True); self.preview_timer.setInterval(650); self.preview_timer.timeout.connect(self.automatic_preview)
        self.watcher=QFileSystemWatcher(self); self.watcher.fileChanged.connect(self.files_changed); self.watcher.directoryChanged.connect(self.files_changed)
        self.setWindowTitle("Change Lens"); self.resize(1440,920); self.setMinimumSize(1120,720)
        root,outer=column(GlassWorkspace()); outer.setContentsMargins(12,8,12,0);outer.setSpacing(8); self.setCentralWidget(root)
        header=QFrame(); header.setObjectName("topbar"); row=QHBoxLayout(header); row.setContentsMargins(20,12,20,12)
        brand=text("CL","brandMark"); brand.setFixedSize(36,36); brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(brand); row.addWidget(text("Change Lens","brand")); row.addSpacing(20)
        self.project_name=text("No workspace open","muted"); row.addWidget(self.project_name,1); row.addWidget(text("LOCAL / PYTHON","badge"))
        self.open_button=action("Open folder",self.open_repository,glyph="folder"); row.addWidget(self.open_button)
        self.save_button=action("Save",self.save_current,glyph="save"); row.addWidget(self.save_button)
        self.changes_button=action("Analyze changes",self.analyze_changes,True,"impact"); row.addWidget(self.changes_button)
        outer.addWidget(header)
        body=QSplitter(Qt.Orientation.Horizontal); body.setHandleWidth(1)
        side,sidebar=column(QFrame(),14); side.setObjectName("sidebar"); side.setMinimumWidth(200)
        sidebar.addWidget(text("WORKSPACE","eyebrow"))
        self.nav=AnimatedNavigation(); self.nav.setObjectName("navigation"); self.nav.setFixedHeight(234)
        for title,glyph in [("Editor","code"),("Change review","branch"),("Impact analysis","impact"),("Test runner","test"),("Refactoring","refactor"),("Diagnostics","info")]:
            item=QListWidgetItem(icon(glyph),title); item.setSizeHint(QSize(180,36)); self.nav.addItem(item)
        self.nav.currentRowChanged.connect(self.navigate); sidebar.addWidget(self.nav)
        explorer_tools=QHBoxLayout(); explorer_tools.addWidget(text("EXPLORER","eyebrow"),1)
        self.reindex_button=action("Refresh",self.reindex); self.reindex_button.setObjectName("smallButton"); explorer_tools.addWidget(self.reindex_button); sidebar.addLayout(explorer_tools)
        self.search=QLineEdit(); self.search.setPlaceholderText("Find file or symbol…"); self.search.textChanged.connect(self.filter_tree); sidebar.addWidget(self.search)
        self.explorer=QTreeWidget(); self.explorer.setHeaderHidden(True); self.explorer.setObjectName("explorer"); self.explorer.setIndentation(14)
        self.explorer.itemClicked.connect(self.explorer_clicked); sidebar.addWidget(self.explorer,1)
        self.repo_summary=text("Open a folder to explore its files.","muted"); sidebar.addWidget(self.repo_summary); body.addWidget(side)
        content,main=column(margins=24)
        headings=QHBoxLayout(); heading,col=column(); col.setSpacing(4)
        self.title=text("Editor","pageTitle"); self.subtitle=text("Your code, changes and analysis in one workspace.","muted"); col.addWidget(self.title); col.addWidget(self.subtitle); headings.addWidget(heading,1)
        self.comparison=QComboBox(); self.comparison.addItem("Automatic (recommended)","auto"); self.comparison.addItem("Git HEAD","git"); self.comparison.addItem("Saved comparison point","baseline"); headings.addWidget(self.comparison)
        self.baseline_button=action("Capture baseline",self.capture_baseline); headings.addWidget(self.baseline_button); main.addLayout(headings)
        self.banner=text("","banner"); self.banner.hide(); main.addWidget(self.banner)
        self.result_state=text("","banner"); self.result_state.hide(); main.addWidget(self.result_state)
        self.pages=AnimatedStack(); self.tabs=self.pages; main.addWidget(self.pages,1)
        body.addWidget(content); body.setSizes([245,1195]); body.setStretchFactor(1,1); outer.addWidget(body,1)
        footer=QFrame(); footer.setObjectName("footer"); line=QHBoxLayout(footer); line.setContentsMargins(18,6,18,6)
        self.status=text("Ready — open a folder or try the sample workspace.","muted"); line.addWidget(self.status,1)
        self.progress=QProgressBar(); self.progress.setFixedWidth(90); self.progress.hide(); line.addWidget(self.progress)
        self.cancel_button=action("Cancel",self.cancel); self.cancel_button.hide(); line.addWidget(self.cancel_button)
        self.position=text("UTF-8","muted"); line.addWidget(self.position); outer.addWidget(footer)
        self.build_editor(); self.build_changes(); self.build_impact(); self.build_tests(); self.build_refactor(); self.build_diagnostics(); self.build_review(); self.build_ai(); self.build_menu()
        self.compact_chrome(sidebar,main,header,heading,headings,brand)
        self.apply_theme(); self.navigate(0); self.refresh_actions()
        self.initialize_ai()

    def compact_chrome(self,sidebar,main,header,heading,headings,brand):
        # The editor owns the window; tools open only when requested.
        self.project_panel = self.explorer.parentWidget()
        self.inspector = self.findChild(QFrame,"inspector")
        self.inspector.hide()
        self.symbols.hide()
        self.outline=QListWidget(); self.outline.setObjectName("outline")
        self.outline.itemClicked.connect(lambda item:self.select_symbol(item.data(Qt.ItemDataRole.UserRole)))
        self.inspector.layout().insertWidget(2,self.outline)
        self.ideas.setMaximumHeight(160)
        self._page_heading=heading; heading.setParent(self); heading.hide()
        main.removeItem(headings)
        reviewbar=QHBoxLayout(); reviewbar.setContentsMargins(12,8,12,8)
        self.comparison_note=text("Comparison is chosen automatically.","muted"); reviewbar.addWidget(self.comparison_note,1)
        self.comparison_advanced=QCheckBox("Advanced"); reviewbar.addWidget(self.comparison_advanced)
        reviewbar.addWidget(self.comparison); reviewbar.addWidget(self.baseline_button); reviewbar.addStretch()
        self.comparison.hide(); self.baseline_button.hide()
        self.comparison_advanced.toggled.connect(self.comparison.setVisible); self.comparison_advanced.toggled.connect(self.baseline_button.setVisible)
        self.pages.widget(1).layout().insertLayout(0,reviewbar)
        main.setContentsMargins(8,0,0,0); main.setSpacing(8)
        sidebar.removeWidget(self.nav)
        self.nav.setParent(None); self.nav.setFlow(QListWidget.Flow.LeftToRight); self.nav.setWrapping(False)
        self.nav.setFixedHeight(42); self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for index,title in enumerate(["Code","Changes","Impact","Tests","Refactor","Diagnostics"]):
            item=self.nav.item(index); item.setText(title); item.setIcon(QIcon()); item.setSizeHint(QSize(94 if index<5 else 110,34))
        review_item=QListWidgetItem("Review"); review_item.setSizeHint(QSize(94,34)); self.nav.addItem(review_item)
        ai_item=QListWidgetItem("Assistant"); ai_item.setSizeHint(QSize(100,34)); self.nav.addItem(ai_item)
        self.nav.currentRowChanged.disconnect(self.navigate)
        for page_index in range(self.nav.count()):self.nav.item(page_index).setData(Qt.ItemDataRole.UserRole,page_index)
        lens_item=self.nav.takeItem(6); lens_item.setText("Lens"); self.nav.insertItem(0,lens_item)
        for row_index in range(self.nav.count()):
            item=self.nav.item(row_index); page_index=item.data(Qt.ItemDataRole.UserRole)
            if page_index==7:item.setText("Brief")
            elif page_index==0:item.setText("Editor")
            elif page_index==1:item.setText("Diff")
            elif page_index==4:item.setText("Fix")
            if page_index in {2,5}:item.setHidden(True)
        self.nav.currentRowChanged.connect(self.navigate_from_nav)
        main.addWidget(self.nav)
        sidebar.setContentsMargins(10,8,8,8); sidebar.setSpacing(6)
        for item in self.project_panel.findChildren(QLabel):
            if item.text()=="WORKSPACE":item.hide()
            elif item.text()=="EXPLORER":item.setText("Project")
        self.search.hide(); self.repo_summary.hide()
        self.reindex_button.setText("Refresh"); self.reindex_button.setToolTip("Refresh project index")
        self.reindex_button.setFixedWidth(56)
        brand.hide()
        for item in header.findChildren(QLabel):
            if item.objectName() in ("brand","badge"):item.hide()
        self.open_button.hide(); self.save_button.hide()
        self.project_name.setObjectName("projectTitle")
        self.project_name.setToolTip("Current project")
        header.layout().setContentsMargins(18,10,12,10)
        self.quick_button=action("Search files…    Ctrl+P",self.quick_open)
        self.quick_button.setObjectName("commandSearch"); self.quick_button.setFixedWidth(280)
        header_row=header.layout()
        while header_row.count():header_row.takeAt(0)
        identity=text("CHANGE LENS","identity"); header_row.addWidget(identity); header_row.addSpacing(14)
        header_row.addWidget(self.project_name); header_row.addStretch(1)
        files_button=action("Files",self.toggle_project); files_button.setObjectName("smallButton"); header_row.addWidget(files_button)
        header_row.addWidget(self.quick_button); header_row.addStretch(1)
        self.format_button=action("Format",self.format_current);self.format_button.setToolTip("Format document · Alt+Shift+F · review before applying");header_row.addWidget(self.format_button)
        self.ai_button=action("Brief",self.open_brief); self.ai_button.setObjectName("smallButton"); header_row.addWidget(self.ai_button); header_row.addWidget(self.changes_button)
        self.changes_button.setText("Follow changes"); self.changes_button.setIcon(QIcon()); self.changes_button.setObjectName("lensAction")
        self.changes_button.setToolTip("Save edits, choose the comparison automatically and review the results")
        self.breadcrumb=text("","breadcrumb")
        self.breadcrumb.hide()
        self.pages.widget(0).layout().setSpacing(0)
        for index in range(1,self.pages.count()):
            self.pages.widget(index).layout().setContentsMargins(14,12,14,10)
        welcome=self.findChild(QFrame,"welcome")
        for item in welcome.findChildren(QLabel):item.hide()
        self.demo_button.setText("Open sample project")
        # Keep the empty state restrained: a few discoverable keyboard actions.
        intro=welcome.layout()
        intro.insertWidget(1,text("Change Lens","emptyTitle"))
        intro.insertWidget(2,text("Open folder                         Ctrl+O\nFind a file                             Ctrl+P\nShow commands                 Ctrl+Shift+P","welcomeText"))
        self.install_workbench_commands()

    def install_workbench_commands(self):
        self.commands=[("Project: Open folder",self.open_repository),("Project: Open sample",self.open_sample),("Project: Open web sample",self.open_web_sample),("Project: Open Flutter sample",self.open_flutter_sample),
            ("Project: Refresh index",self.reindex),("Project: Capture baseline",self.capture_baseline),
            ("Editor: Save",self.save_current),("Editor: Find in file",self.find_in_file),("Search: Find in project",self.search_project),("Editor: Format document",self.format_current),
            ("Analysis: Analyze changes",self.analyze_changes),("Analysis: Analyze symbol under cursor",self.analyze_selected),
            ("Refactor: Preview rename",self.prepare_rename),("View: Toggle project panel",self.toggle_project),
            ("View: Toggle outline",self.toggle_outline)]
        self.commands.insert(0,("Project: Check project",self.analyze_changes))
        self.commands.extend([("AI: Complete code locally",self.request_ai_completion),("AI: Explain current code",self.explain_code),("AI: Suggest improvement",self.suggest_rewrite)])
        menu=self.menuBar().addMenu("View")
        from PySide6.QtWidgets import QApplication
        try:reduce=bool(json.loads((app_dir()/'appearance.json').read_text(encoding='utf-8')).get('reduce_motion',False))
        except (OSError,ValueError):reduce=False
        QApplication.instance().setProperty('reduceMotion',reduce)
        motion_action=QAction('Reduce motion',self);motion_action.setCheckable(True);motion_action.setChecked(reduce)
        def motion_toggled(value):
            QApplication.instance().setProperty('reduceMotion',value);self.pages.finish_transition();self.nav.stop_motion()
            (app_dir()/'appearance.json').write_text(json.dumps({'reduce_motion':value}),encoding='utf-8')
        motion_action.toggled.connect(motion_toggled);menu.addAction(motion_action)
        for title,shortcut,callback in [("Find file…","Ctrl+P",self.quick_open),("Command palette…","Ctrl+Shift+P",self.command_palette),
                ("Toggle project panel","Ctrl+B",self.toggle_project),("Toggle outline","Ctrl+Shift+O",self.toggle_outline),
                ("Return to code","Ctrl+1",lambda:self.navigate(0))]:
            item=QAction(title,self); item.setShortcut(QKeySequence(shortcut)); item.triggered.connect(callback); menu.addAction(item)
        for index,title in enumerate(["Editor","Diff","Evidence table","Tests","Fix","Diagnostics","Lens","Brief"]):
            callback=lambda checked=False,i=index:self.navigate(i)
            item=QAction(title,self); item.triggered.connect(callback); menu.addAction(item)
            self.commands.append(("View: "+title,callback))

    def toggle_project(self):
        self.project_panel.setVisible(self.project_panel.isHidden())

    def navigate_from_nav(self,row):
        if row>=0:self.navigate(self.nav.item(row).data(Qt.ItemDataRole.UserRole))

    def toggle_outline(self):
        self.navigate(0); self.inspector.setVisible(self.inspector.isHidden())

    def show_picker(self,title,entries):
        from .palette import Picker
        self.picker=Picker(self,title,entries)
        self.picker.move(self.mapToGlobal(self.rect().topLeft())+self.rect().center()-self.picker.rect().center())
        self.picker.show(); self.picker.query.setFocus()

    def command_palette(self):
        self.show_picker("Type a command…",self.commands)

    def quick_open(self):
        entries=[]
        if self.snapshot:
            root=Path(self.snapshot.root)
            for relative in self.project_files:
                entries.append((relative,lambda p=root/relative:self.open_from_picker(p)))
        self.show_picker("Find a file in this project…",entries)

    def open_from_picker(self,path):
        self.open_file(path); self.navigate(0)

    def build_editor(self):
        page,layout=column(); split=QSplitter(Qt.Orientation.Horizontal)
        self.editor_stack=QStackedWidget()
        welcome,intro=column(QFrame(),44); welcome.setObjectName("welcome"); intro.addStretch()
        intro.addWidget(text("A clearer view of\nyour next change.","hero")); intro.addWidget(text("Explore code. Follow dependencies. Review every change.","welcomeText")); intro.addSpacing(18)
        self.demo_button=action("Open sample project",self.open_sample,True,"code"); intro.addWidget(self.demo_button,0,Qt.AlignmentFlag.AlignLeft)
        intro.addWidget(action("Open your project folder",self.open_repository,glyph="folder"),0,Qt.AlignmentFlag.AlignLeft); intro.addSpacing(24)
        intro.addWidget(action("Try JavaScript / React sample",self.open_web_sample),0,Qt.AlignmentFlag.AlignLeft)
        for title,body in [("01  WRITE","Syntax highlighting, line numbers and optional local code completion."),("02  REVIEW","Compare your saved edits with Git or a captured baseline."),("03  VERIFY","Trace affected code and choose tests with inspectable evidence.")]:
            intro.addWidget(text(title,"eyebrow")); intro.addWidget(text(body,"muted"))
        intro.addStretch(); self.editor_stack.addWidget(welcome)
        panel,col=column(); col.setSpacing(0)
        from .find_ui import FindBar
        self.find_panel=FindBar(self.current_editor,self.search_project,self);self.find_bar=self.find_panel.query;col.addWidget(self.find_panel)
        self.editor_tabs=QTabWidget(); self.editor_tabs.setTabsClosable(True); self.editor_tabs.setDocumentMode(True); self.editor_tabs.setMovable(True)
        self.editor_tabs.tabBar().setDrawBase(False)
        self.editor_tabs.currentChanged.connect(self.editor_changed); self.editor_tabs.tabCloseRequested.connect(self.close_document); col.addWidget(self.editor_tabs,1)
        self.editor_stack.addWidget(panel); split.addWidget(self.editor_stack)
        detail,inspector=column(QFrame(),16); detail.setObjectName("inspector"); detail.setMinimumWidth(215); detail.setMaximumWidth(300)
        inspector.addWidget(text("CODE INTELLIGENCE","eyebrow")); inspector.addWidget(text("Understand this symbol","sectionTitle"))
        self.symbols=QComboBox(); self.symbols.setMinimumContentsLength(12); self.symbols.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.symbols.activated.connect(lambda:self.select_symbol(self.symbols.currentData())); inspector.addWidget(self.symbols)
        self.selected_button=action("Analyze symbol",self.analyze_selected,True,"impact"); inspector.addWidget(self.selected_button)
        self.symbol_info=text("Choose a function or class in the explorer.","muted"); inspector.addWidget(self.symbol_info); inspector.addSpacing(14)
        inspector.addWidget(text("REFACTORING IDEAS","eyebrow")); self.ideas=QListWidget(); self.ideas.setWordWrap(True); self.ideas.itemClicked.connect(self.idea_clicked); inspector.addWidget(self.ideas,1)
        inspector.addWidget(text("LOCAL COMPLETION","eyebrow")); inspector.addWidget(text("Ctrl+Space suggests names, attributes and imports. Enter or Tab accepts a suggestion.","muted"))
        inspector.addSpacing(10); inspector.addWidget(text("SHORTCUTS","eyebrow")); inspector.addWidget(text("Ctrl+S  Save\nCtrl+F  Find in file\nF2  Preview rename","muted"))
        split.addWidget(detail); split.setSizes([800,260]); split.setStretchFactor(0,1); layout.addWidget(split); self.pages.addWidget(page)

    def build_changes(self):
        page,layout=column(); self.change_summary=text("Save edits, then compare them with Git HEAD or a saved baseline.","muted"); layout.addWidget(self.change_summary)
        split=QSplitter(Qt.Orientation.Horizontal); self.change_list=QListWidget(); self.change_list.setMaximumWidth(260); self.change_list.currentRowChanged.connect(self.show_change); split.addWidget(self.change_list)
        self.changes_view=DiffViewer(); split.addWidget(self.changes_view); split.setSizes([220,840]); split.setStretchFactor(1,1); layout.addWidget(split,1); self.pages.addWidget(page)

    def build_impact(self):
        page,layout=column(); cards=QHBoxLayout(); self.metrics={}
        for key,title in [("changed_symbols","CHANGED / SELECTED"),("affected_files","AFFECTED FILES"),("recommended_tests","SUGGESTED TESTS"),("seconds","ANALYSIS TIME")]:
            card,col=column(QFrame(),16); card.setObjectName("metricCard"); col.addWidget(text(title,"eyebrow")); value=text("—","metricValue"); col.addWidget(value); self.metrics[key]=value; cards.addWidget(card)
        layout.addLayout(cards); self.impact_summary=text("Analyze saved changes or a selected symbol.","muted"); layout.addWidget(self.impact_summary)
        split=QSplitter(Qt.Orientation.Horizontal); self.impact_view=QTreeWidget(); self.impact_view.setHeaderLabels(["Affected code","Relationship","Location"]); self.impact_view.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.impact_view.itemClicked.connect(self.impact_clicked); split.addWidget(self.impact_view)
        details,col=column(); self.evidence_title=text("Inspect a relationship","sectionTitle"); self.evidence_reason=text("Click affected code to inspect its source and evidence.","muted")
        col.addWidget(self.evidence_title); col.addWidget(self.evidence_reason); self.source_view=CodeEditor(True); col.addWidget(self.source_view,1); col.addWidget(action("Open in editor",self.open_evidence,glyph="code")); split.addWidget(details)
        split.setSizes([570,490]); layout.addWidget(split,1); self.export_button=action("Export analysis…",self.export_report); layout.addWidget(self.export_button,0,Qt.AlignmentFlag.AlignRight); self.pages.addWidget(page)

    def build_tests(self):
        page,layout=column(); row=QHBoxLayout(); self.test_summary=text("Recommendations explain their evidence. Choose which tests to run.","muted"); row.addWidget(self.test_summary,1)
        self.show_weak=QCheckBox("Include name-only / weak matches"); self.show_weak.toggled.connect(self.populate_tests); row.addWidget(self.show_weak); layout.addLayout(row)
        split=QSplitter(Qt.Orientation.Vertical); self.test_table=QTableWidget(0,4); self.test_table.setHorizontalHeaderLabels(["Test","Evidence","Score","Run"])
        self.test_table.itemChanged.connect(self.test_choice_changed)
        self.test_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); self.test_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers); self.test_table.verticalHeader().hide(); self.test_table.setShowGrid(False); self.test_table.setAlternatingRowColors(True)
        self.test_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents); self.test_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch); self.test_table.cellClicked.connect(self.show_test_features); split.addWidget(self.test_table)
        bottom,col=column(); self.test_reason=text("Select a test to inspect why it is recommended.","muted"); col.addWidget(self.test_reason)
        tools=QHBoxLayout(); self.interpreter=QLineEdit(); self.interpreter.setPlaceholderText("Python interpreter or node.exe (project dependencies required)"); tools.addWidget(self.interpreter,1); self.interpreter_browse=action("Browse…",self.choose_interpreter); tools.addWidget(self.interpreter_browse)
        self.timeout=QSpinBox(); self.timeout.setRange(10,3600); self.timeout.setValue(120); self.timeout.setSuffix(" s"); tools.addWidget(self.timeout)
        self.test_advanced=QCheckBox("Advanced run options"); tools.addWidget(self.test_advanced)
        for widget in (self.interpreter,self.interpreter_browse,self.timeout):widget.hide(); self.test_advanced.toggled.connect(widget.setVisible)
        tools.addStretch()
        self.validate_button=action("Run selected tests",self.check_and_run,True,"test"); tools.addWidget(self.validate_button)
        self.mutate_button=action("Demo fault check",lambda:self.validate_demo(True)); tools.addWidget(self.mutate_button); col.addLayout(tools)
        self.run_summary=text("Not run · Tests execute saved source, not preview patches.","muted"); col.addWidget(self.run_summary)
        self.validation_view=QPlainTextEdit(); self.validation_view.setReadOnly(True); self.validation_view.setObjectName("terminal"); self.validation_view.setFont(QFont("Noto Sans Mono",10)); col.addWidget(self.validation_view,1)
        split.addWidget(bottom); split.setSizes([350,280]); layout.addWidget(split,1); self.pages.addWidget(page)

    def build_refactor(self):
        page,layout=column(); layout.addWidget(text("Place the editor cursor on a name, or select code to extract. Review the resulting patch before applying it.","muted"))
        row=QHBoxLayout(); self.operation=QComboBox()
        for title,value in [("Rename symbol across files","rename"),("Extract helper from selection","extract_method"),("Extract variable from expression","extract_variable")]:self.operation.addItem(title,value)
        self.operation.addItem("Local AI suggested improvement","ai_rewrite")
        row.addWidget(self.operation,1); self.old_name=QLineEdit(); self.old_name.setReadOnly(True); self.old_name.setPlaceholderText("Name under cursor"); row.addWidget(self.old_name)
        self.new_name=QLineEdit(); self.new_name.setPlaceholderText("New name…"); row.addWidget(self.new_name)
        self.new_name.textEdited.connect(self.schedule_preview)
        self.operation.activated.connect(self.schedule_preview)
        self.preview_button=action("Preview changes",self.preview,True,"refactor"); row.addWidget(self.preview_button); self.patch_button=action("Export patch…",self.export_patch); row.addWidget(self.patch_button); layout.addLayout(row)
        self.operation.currentIndexChanged.connect(self.refactor_mode_changed)
        apply_row=QHBoxLayout(); apply_row.addWidget(text("Original files stay unchanged until you apply a reviewed preview. A recovery backup is saved first.","muted"),1)
        self.apply_button=action("Apply reviewed patch",self.apply_patch,True,"test"); apply_row.addWidget(self.apply_button); layout.addLayout(apply_row)
        self.refactor_context=text("Open a Python file in the editor first.","muted"); layout.addWidget(self.refactor_context)
        split=QSplitter(Qt.Orientation.Horizontal); self.patch_list=QListWidget(); self.patch_list.setMaximumWidth(260); self.patch_list.currentRowChanged.connect(self.show_patch_file); split.addWidget(self.patch_list)
        self.diff_view=DiffViewer(); split.addWidget(self.diff_view); split.setSizes([220,840]); split.setStretchFactor(1,1); layout.addWidget(split,1); self.pages.addWidget(page)

    def build_diagnostics(self):
        page,layout=column(); self.diagnostic_summary=text("Analysis issues and unsupported relationships appear here.","muted"); layout.addWidget(self.diagnostic_summary)
        self.diagnostic_search=QLineEdit(); self.diagnostic_search.setPlaceholderText("Filter diagnostics…"); self.diagnostic_search.textChanged.connect(self.populate_diagnostics); layout.addWidget(self.diagnostic_search)
        self.diagnostics=QListWidget(); self.diagnostics.setWordWrap(True); layout.addWidget(self.diagnostics,1)
        self.train_button=action("Retrain experimental test ranker",self.train); layout.addWidget(self.train_button,0,Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(text("Jedi provides static completion; Rope generates refactoring previews. The small trained model only ranks tests. These features do not generate arbitrary code or prove safety.","muted")); self.pages.addWidget(page)

    def build_review(self):
        page,layout=column(); layout.setSpacing(18)
        self.review_title=text("CHANGE INVESTIGATION","eyebrow"); self.review_title.hide()
        self.review_context=text("Comparison setup and test selection are automatic.","muted"); layout.addWidget(self.review_context)
        self.review_detail=text("","sectionTitle"); self.review_detail.hide()
        self.lens_view=ChangeLens()
        self.lens_view.focusUpdated.connect(self.refresh_actions)
        self.lens_view.traceRequested.connect(lambda sid:(self.select_symbol(sid),self.analyze_selected()))
        self.lens_view.codeRequested.connect(lambda sid:(self.select_symbol(sid),self.navigate(0)))
        self.lens_view.explainRequested.connect(self.explain_impact)
        layout.addWidget(self.lens_view,1)
        row=QHBoxLayout(); self.review_diff=action("Read diffs",lambda:self.navigate(1)); row.addWidget(self.review_diff)
        self.review_tests=action("Run linked tests",self.check_and_run,True); row.addWidget(self.review_tests)
        self.review_tests.setObjectName("lensAction")
        row.addWidget(action("Evidence table",lambda:self.navigate(2))); row.addStretch(); layout.addLayout(row)
        self.review_issue=action("Inspect source issues",lambda:self.navigate(5)); self.review_issue.hide(); layout.addWidget(self.review_issue)
        self.review_items=QTreeWidget(page); self.review_items.setHeaderLabels(["What needs attention","Details"])
        self.review_items.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.review_items.itemActivated.connect(self.review_item_opened); self.review_items.hide()
        self.review_tests.setToolTip("Analyze the focused function if needed, then run its selected tests. Repository trust is required on first execution.")
        self.pages.addWidget(page)

    def populate_review(self):
        if not self.report:return
        report=self.report; summary=report["summary"]; context=report.get("comparison_context",{})
        changed=len(report["changes"]["files"]); selected=report["comparison"]=="symbol"
        self.review_title.setText("Symbol review" if selected else "Changes ready to review" if changed else "Ready — watching for your next change")
        description=context.get("label","Automatic comparison")
        if context.get("created"):description+=". First comparison point recorded; earlier edits are unavailable."
        self.review_context.setText(description)
        profile=self.snapshot.profile
        languages=sorted({NAMES[name] for name in profile.get("languages",{})})
        frameworks=sorted({row["name"] for row in profile.get("frameworks",[])})
        if languages:self.review_context.setText(description+" · "+", ".join(languages)+( " · "+", ".join(frameworks) if frameworks else ""))
        structural=[NAMES[name] for name in profile.get("languages",{}) if name in {"java","csharp","go","rust"}]
        if structural:self.review_context.setText(self.review_context.text()+" · File/module analysis only: "+", ".join(structural))
        self.review_context.setToolTip("Frameworks are declaration hints. See View → Diagnostics for language capabilities and unsupported areas.")
        self.comparison_note.setText(description)
        self.review_detail.setText(f"{changed} changed files · {summary['affected_symbols']} potentially affected symbols · {summary['recommended_tests']} recommended tests")
        self.review_items.clear()
        for row in report["changes"]["files"]:
            item=QTreeWidgetItem(self.review_items,[row["path"],row["status"]]); item.setData(0,Qt.ItemDataRole.UserRole,("change",row["path"]))
        for sid in report["possible_gaps"]:
            item=QTreeWidgetItem(self.review_items,[sid,"No test dependency found; inspect this code"]); item.setData(0,Qt.ItemDataRole.UserRole,("symbol",sid))
        for warning in report["warnings"]:
            if warning.startswith(("Cannot parse","Skipped")):
                item=QTreeWidgetItem(self.review_items,["Source needs attention",warning]); item.setData(0,Qt.ItemDataRole.UserRole,("diagnostics",None))
        self.review_diff.setEnabled(bool(changed)); self.review_tests.setEnabled(bool(summary["recommended_tests"]))
        issues=sum(warning.startswith(("Cannot parse","Skipped")) for warning in report["warnings"])
        self.review_issue.setVisible(bool(issues)); self.review_issue.setText(f"{issues} source issues need attention — inspect diagnostics")
        self.lens_view.set_report(self.snapshot,report)
        linked=bool(self.lens_view.linked_tests)
        self.review_tests.setEnabled(bool(summary["recommended_tests"]) or linked)

    def review_item_opened(self,item,column=0):
        kind,value=item.data(0,Qt.ItemDataRole.UserRole)
        if kind=="change":
            self.change_list.setCurrentRow(next(i for i,row in enumerate(self.change_rows) if row["path"]==value)); self.navigate(1)
        elif kind=="symbol":self.select_symbol(value); self.navigate(0)
        else:self.navigate(5)

    def check_and_run(self):
        if self.worker:return
        focused=self.lens_view.focus.currentData() if self.report else None
        if self.pages.currentIndex()==6 and focused in (self.snapshot.symbols if self.snapshot else {}) and focused not in self.report['changes']['seeds']:
            self.analyze([focused],run_after=True);return
        if self.report and not self.report["tests"] and self.lens_view.focus.currentData():
            sid=self.lens_view.focus.currentData(); symbol=self.snapshot.symbols.get(sid)
            if symbol:self.analyze([sid],run_after=True); return
        if self.report_stale or not self.report:
            self.analyze(None,run_after=True)
        else:
            if self.pages.currentIndex()==6:
                for row in self.report["tests"]:self.test_choices[row["symbol"]]=row["symbol"] in self.lens_view.linked_tests
                self.populate_tests()
            self.validate_demo(False)

    def build_menu(self):
        for menu_name,items in [("File",[("Open folder…","Ctrl+O",self.open_repository),("Save","Ctrl+S",self.save_current),("Save all","Ctrl+Shift+S",self.save_all)]),("Edit",[("Find in file","Ctrl+F",self.find_in_file),("Format document","Alt+Shift+F",self.format_current),("Complete Python","Ctrl+Space",self.request_completion),("Preview rename","F2",self.prepare_rename)])]:
            menu=self.menuBar().addMenu(menu_name)
            for title,shortcut,callback in items:
                item=QAction(title,self); item.setShortcut(QKeySequence(shortcut)); item.triggered.connect(callback); menu.addAction(item)
        for title,shortcut,callback in [('Search project','Ctrl+Shift+F',lambda:self.search_project()),('Next match','F3',self.find_next),('Previous match','Shift+F3',lambda:self.find_panel.step(-1))]:
            item=QAction(title,self);item.setShortcut(QKeySequence(shortcut));item.triggered.connect(callback);menu.addAction(item)

    def apply_theme(self):
        self.setStyleSheet(STYLESHEET)
        close_icon=(resources()/"icons"/"close.svg").as_posix()
        self.setStyleSheet(self.styleSheet()+f"QTabBar::close-button {{ image: url({close_icon}); width:14px; height:14px; }}")

    def navigate(self,index):
        if not hasattr(self,"pages") or index<0:return
        self.pages.setCurrentIndex(index)
        self.position.setVisible(index not in {6,7})
        if hasattr(self,"project_panel"):
            if index in {6,7}:self.project_panel.hide()
            elif index==0:self.project_panel.setVisible(self.snapshot is not None)
        self.nav.blockSignals(True)
        for nav_index in range(self.nav.count()):
            if self.nav.item(nav_index).data(Qt.ItemDataRole.UserRole)==index:self.nav.setCurrentRow(nav_index); break
        self.nav.blockSignals(False)
        self.nav.glide_to_current()
        titles=[("Editor","Write and explore with offline Python intelligence."),("Change review","Read old and new code side by side."),("Impact analysis","Follow evidence from changed code to potential callers."),("Test runner","Choose relevant tests and inspect actual results."),("Refactoring","Preview structural changes across your project."),("Diagnostics","Inspect analysis limits and model status."),("Review","Your project check and next steps."),("Assistant","Local coding models.")]
        self.title.setText(titles[index][0]); self.subtitle.setText(titles[index][1])
        if index==4:self.update_refactor_context()
        if hasattr(self,'format_button'):self.format_button.setVisible(index==0 and self.current_document() is not None)

    def notify(self,message,error=False):
        self.status.setText(message.splitlines()[0][:180]); self.banner.setText(message); self.banner.setVisible(error)

    def refresh_actions(self):
        busy=self.worker is not None; opened=self.snapshot is not None
        self.open_button.setEnabled(not busy); self.demo_button.setEnabled(not busy)
        for widget in (self.reindex_button,self.changes_button,self.baseline_button,self.selected_button):widget.setEnabled(opened and not busy)
        self.save_button.setEnabled(self.current_editor() is not None and not busy); self.preview_button.setEnabled(self.current_editor() is not None and not busy)
        editor=self.current_editor();document=self.current_document()
        if hasattr(self,'format_button'):
            self.format_button.setVisible(self.pages.currentIndex()==0 and document is not None)
            self.format_button.setEnabled(bool(editor and document and not editor.isReadOnly() and formatter_for(document.path)) and not busy)
        if self.current_document() and language_for(self.current_document().path)!="python" and self.operation.currentData()!='ai_rewrite':
            self.preview_button.setEnabled(False); self.preview_button.setToolTip("Select Local AI suggested improvement for a reviewed proposal in this language. Structural rename/extract is Python-only.")
        else:self.preview_button.setToolTip("")
        if self.operation.currentData()=='ai_rewrite' and getattr(self,'ai_worker',None):self.preview_button.setEnabled(False)
        self.patch_button.setEnabled(self.patch is not None and not self.patch_stale and not busy); self.apply_button.setEnabled(self.patch is not None and not self.patch_stale and not busy); self.export_button.setEnabled(self.report is not None and not busy)
        executable=execution_family(self.snapshot,self.checked_tests())
        self.validate_button.setEnabled(bool(executable) and not self.report_stale and not busy); self.train_button.setEnabled(not busy)
        self.validate_button.setToolTip("Runs selected Python tests, JS/TS files/filters, or Flutter test files with prepared SDK/dependencies. Repository trust is required.")
        self.mutate_button.setVisible(opened and Path(self.snapshot.root)==(resources()/"demo").resolve()); self.mutate_button.setEnabled(self.report is not None and not self.report_stale and not busy)
        if hasattr(self,"review_tests"):
            linked=bool(self.report and self.lens_view.linked_tests)
            self.review_tests.setEnabled(bool(self.report and linked and execution_family(self.snapshot,list(self.lens_view.linked_tests))) and not busy)
            self.review_tests.setToolTip("Python, JS/TS and prepared Flutter test execution. Other languages currently provide structural recommendations.")

    def update_result_state(self):
        if self.report and self.report["snapshot"] != self.snapshot.id:self.report_stale=True
        messages=[]
        if self.report_stale and self.report:messages.append("Code changed. Checks refresh after you save, or use Check project now.")
        if self.patch_stale and self.patch:messages.append("Refactoring preview needs a refresh before Apply.")
        self.result_state.setText(" ".join(messages)); self.result_state.setVisible(bool(messages))
        self.refresh_actions()

    def invalidate_results(self):
        self.report_stale=bool(self.report); self.patch_stale=bool(self.patch)
        self.update_result_state()

    def start(self,task,callback,stream=False):
        if self.worker is not None:return
        self._pending_result=self._pending_error=None; self.banner.hide(); self.progress.setRange(0,0); self.progress.show(); self.cancel_button.show()
        self.worker=Worker(task,self)
        self.worker.message.connect(lambda message:self.validation_view.setPlainText(message) if stream else self.status.setText(message[:160]))
        self.worker.done.connect(lambda result:setattr(self,"_pending_result",result)); self.worker.failed.connect(lambda error:setattr(self,"_pending_error",error)); self.worker.finished.connect(lambda:self.finish(callback))
        self.refresh_actions(); self.worker.start()

    def finish(self,callback):
        worker=self.worker; self.worker=None; worker.deleteLater(); self.progress.hide(); self.cancel_button.hide()
        if self._pending_error:self.notify(self._pending_error,True)
        else:
            try:callback(self._pending_result)
            except Exception as exc:self.notify(str(exc),True)
        self.refresh_actions()
        if self.pending_check and self.worker is None:self.check_timer.start()

    def cancel(self):
        self.pending_check=False; self.check_timer.stop(); self.preview_timer.stop()
        if self.worker:self.worker.cancel.set(); self.status.setText("Cancelling…")

    def current_editor(self):
        return self.editor_tabs.currentWidget() if hasattr(self,"editor_tabs") else None

    def current_document(self):
        return self.documents.get(self.current_editor())

    def open_repository(self):
        path=QFileDialog.getExistingDirectory(self,"Open source workspace")
        if path:self.open_path(Path(path))

    def open_sample(self):
        import shutil
        root=app_dir()/"sample-project"
        root.mkdir(parents=True,exist_ok=True)
        for filename in json.loads((resources()/"demo_manifest.json").read_text(encoding="utf-8")):
            target=root/filename
            if not target.exists():shutil.copy2(resources()/"demo"/filename,target)
        self.open_path(root)

    def open_web_sample(self):
        import shutil
        root=app_dir()/"web-sample"; source=resources()/"web_demo"
        for path in source.rglob("*"):
            if not path.is_file():continue
            target=root/path.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():shutil.copy2(path,target)
        self.open_path(root)

    def open_flutter_sample(self):
        import shutil
        root=app_dir()/'flutter-sample';source=resources()/'flutter_demo'
        for path in source.rglob('*'):
            if not path.is_file():continue
            target=root/path.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():shutil.copy2(path,target)
        self.open_path(root)

    def confirm_unsaved(self):
        if not any(editor.document().isModified() for editor in self.documents):return True
        reply=QMessageBox.question(self,"Unsaved files","Save edits before switching workspace?",QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Save)
        if reply==QMessageBox.StandardButton.Cancel:return False
        return self.save_all() if reply==QMessageBox.StandardButton.Save else True

    def open_path(self,path):
        if self.confirm_unsaved():
            self.check_timer.stop(); self.preview_timer.stop(); self.pending_check=False
            paths=self.watcher.files()+self.watcher.directories()
            if paths:self.watcher.removePaths(paths)
            def opened(result):
                self.indexed(result[0]); self.analyzed(result,False); self.navigate(6)
            self.start(lambda cancel,progress:analyze_workspace(Path(path),comparison="auto",model_path=self.model_path(),cancel=cancel,progress=progress),opened)

    def files_changed(self,path):
        if self.snapshot:
            self.invalidate_results(); self.pending_check=True; self.check_timer.start()

    def update_watchers(self):
        desired=set(self.report.get("watch_directories",[])) if self.report else set()
        if self.snapshot:
            desired.update(str(Path(self.snapshot.root)/path) for path in self.snapshot.hashes)
            git_dir=Path(self.snapshot.root)/".git"
            desired.update(str(path) for path in (git_dir,git_dir/"HEAD",git_dir/"refs"/"heads") if path.exists())
        current=set(self.watcher.files()+self.watcher.directories())
        if current-desired:self.watcher.removePaths(sorted(current-desired))
        if desired-current:self.watcher.addPaths(sorted(path for path in desired-current if Path(path).exists()))

    def automatic_check(self):
        if not self.snapshot:return
        if self.worker is not None or any(editor.document().isModified() for editor in self.documents):
            self.pending_check=True; return
        self.pending_check=False
        root=Path(self.snapshot.root); mode=self.comparison.currentData(); model=self.model_path()
        def checked(result):
            snapshot,report=result
            if self.report and self.report["snapshot"]==snapshot.id:
                self.report_stale=False
                self.patch_stale=bool(self.patch and self.patch["snapshot"]!=snapshot.id)
                self.report["watch_directories"]=report["watch_directories"]
                self.update_result_state(); self.update_watchers()
            else:self.analyzed(result,False)
        self.start(lambda cancel,progress:analyze_workspace(root,comparison=mode,model_path=model,cancel=cancel,progress=progress),checked)

    def automatic_preview(self):
        if self.pages.currentIndex()!=4 or not self.new_name.text().strip().isidentifier():return
        if self.worker:self.preview_timer.start(); return
        self.preview()

    def schedule_preview(self,*args):
        if self.operation.currentData()=='ai_rewrite':self.preview_timer.stop();return
        if self.patch:
            self.patch_stale=True; self.update_result_state()
        self.preview_timer.start()

    def reindex(self):
        if self.snapshot:self.analyze(None)

    def indexed(self,snapshot,preserve=False):
        if not preserve:
            self.editor_tabs.blockSignals(True); self.editor_tabs.clear(); self.documents.clear(); self.editors.clear(); self.editor_tabs.blockSignals(False)
        self.snapshot=snapshot; self.report=self.patch=None; self.project_name.setText(Path(snapshot.root).name); self.project_name.setToolTip(snapshot.root)
        self.report_stale=self.patch_stale=False; self.test_choices.clear(); self.result_state.hide()
        from .flutter_sdk import detect_sdk
        sdk=detect_sdk() if 'dart' in snapshot.profile.get('languages',{}) else None
        self.interpreter.setText(detect_interpreter(Path(snapshot.root)) if "python" in snapshot.profile.get("languages",{}) else str(sdk['dart']) if sdk else detect_node(Path(snapshot.root))); self.comparison.setCurrentIndex(0)
        self.populate_symbols(); self.populate_explorer(); self.populate_diagnostics(); self.repo_summary.setText(f"{len(snapshot.hashes)} indexed files · {len(snapshot.symbols)} symbols")
        if not preserve:
            self.navigate(0); preferred="invoice.py" if "invoice.py" in snapshot.hashes else next((p for p in snapshot.hashes if is_source(p) and Path(p).name!="__init__.py"),None)
            if preferred:self.open_file(preferred)
        self.notify(f"Workspace ready · {len(snapshot.edges)} relationships indexed."); self.refresh_actions()

    def populate_symbols(self):
        previous=self.symbols.currentData(); self.symbols.blockSignals(True); self.symbols.clear()
        for sid,symbol in sorted(self.snapshot.symbols.items()):
            if not symbol.is_test and symbol.kind in {"function","async_function","class"}:self.symbols.addItem(symbol.qualname+" · "+symbol.path,sid)
        preferred=previous if previous in self.snapshot.symbols else "invoice.py:calculate_invoice_total"
        index=self.symbols.findData(preferred)
        if index>=0:self.symbols.setCurrentIndex(index)
        self.symbols.blockSignals(False)

    def populate_explorer(self):
        root=Path(self.snapshot.root); paths=set(self.snapshot.hashes); grouped={}
        for symbol in self.snapshot.symbols.values():grouped.setdefault(symbol.path,[]).append(symbol)
        for directory,dirs,files in os.walk(root,followlinks=False):
            dirs[:]=sorted(d for d in dirs if d not in EXCLUDED and not (Path(directory)/d).is_symlink())
            for filename in files:
                target=Path(directory)/filename
                if not target.is_symlink() and target.suffix in {".md",".toml",".txt",".json",".yaml",".yml",".ini",".cfg"}:paths.add(target.relative_to(root).as_posix())
            if len(paths)>2000:break
        signature=(self.snapshot.root,tuple(sorted(paths)),tuple(sorted((s.id,s.name,s.kind) for s in self.snapshot.symbols.values() if '.' not in s.qualname)))
        self.project_files=sorted(paths)
        if getattr(self,'_explorer_signature',None)==signature:return
        self._explorer_signature=signature
        from PySide6.QtWidgets import QTreeWidgetItemIterator
        def key(item):
            data=item.data(0,Qt.ItemDataRole.UserRole)
            if data:return ('file',data['path'],data.get('symbol'))
            parts=[];node=item
            while node is not None:parts.append(node.text(0));node=node.parent()
            return ('folder','/'.join(reversed(parts)))
        old_keys=set();expanded=set();iterator=QTreeWidgetItemIterator(self.explorer)
        while iterator.value():
            item=iterator.value();value=key(item);old_keys.add(value)
            if item.isExpanded():expanded.add(value)
            iterator+=1
        old_root=getattr(self,'_explorer_root',None);self._explorer_root=self.snapshot.root
        selected=key(self.explorer.currentItem()) if self.explorer.currentItem() else None
        scroll=self.explorer.verticalScrollBar().value()
        self.explorer.clear();folders={"":self.explorer.invisibleRootItem()}
        for path in sorted(paths):
            parent=""
            for part in Path(path).parts[:-1]:
                name=(parent+"/"+part).strip("/")
                if name not in folders:folders[name]=QTreeWidgetItem(folders[parent],[part]); folders[name].setIcon(0,icon("folder"))
                parent=name
            item=QTreeWidgetItem(folders[parent],[Path(path).name]); item.setIcon(0,icon("code" if is_source(path) else "file")); item.setData(0,Qt.ItemDataRole.UserRole,{"path":path}); item.setToolTip(0,path)
            for symbol in sorted(grouped.get(path,[]),key=lambda s:s.start):
                if "." in symbol.qualname:continue
                child=QTreeWidgetItem(item,[symbol.name+("()" if symbol.kind!="class" else "")]); child.setIcon(0,icon("test" if symbol.is_test else "code","#a6abb3")); child.setData(0,Qt.ItemDataRole.UserRole,{"path":path,"symbol":symbol.id})
        # Folders expand, while per-file symbols remain available on demand.
        iterator=QTreeWidgetItemIterator(self.explorer)
        while iterator.value():
            item=iterator.value();value=key(item)
            item.setExpanded(value in expanded or value[0]=='folder' and (old_root!=self.snapshot.root or value not in old_keys))
            if value==selected:self.explorer.setCurrentItem(item)
            iterator+=1
        if old_root==self.snapshot.root:self.explorer.verticalScrollBar().setValue(scroll)

    def filter_tree(self,query):
        needle=query.casefold()
        def visit(item):
            matched=needle in item.text(0).casefold(); children=False
            for i in range(item.childCount()):children=visit(item.child(i)) or children
            item.setHidden(not(matched or children))
            if needle and children:item.setExpanded(True)
            return matched or children
        for index in range(self.explorer.topLevelItemCount()):visit(self.explorer.topLevelItem(index))

    def explorer_clicked(self,item,column):
        data=item.data(0,Qt.ItemDataRole.UserRole)
        if data:
            self.open_file(data["path"])
            if data.get("symbol"):self.select_symbol(data["symbol"])
            self.navigate(0)

    @atomic_paint
    def open_file(self,path,line=None):
        if not self.snapshot:return
        target=(Path(self.snapshot.root)/path).resolve()
        if not target.is_relative_to(Path(self.snapshot.root)) or target.is_symlink():return
        editor=self.editors.get(path)
        if editor is None:
            try:
                if target.stat().st_size>2_000_000:raise ValueError("This file exceeds the editor's 2 MB limit.")
                document=Document(target)
            except (OSError,UnicodeError,ValueError) as exc:self.notify(str(exc),True);return
            template=Path(self.snapshot.root)==(resources()/"demo").resolve()
            editor=CodeEditor(readonly=template); editor.set_code(document.text)
            editor.set_language(target)
            self.documents[editor]=document; self.editors[path]=editor; self.editor_tabs.addTab(editor,icon("code"),target.name)
            editor.document().modificationChanged.connect(lambda modified,e=editor:self.mark_modified(e,modified)); editor.saveRequested.connect(self.save_current)
            editor.completionRequested.connect(self.request_completion); editor.positionChanged.connect(self.position.setText); editor.cursorPositionChanged.connect(self.cursor_symbol)
            editor.automaticCompletionRequested.connect(lambda:self.request_completion(True))
            editor.aiCompletionRequested.connect(self.request_ai_completion); editor.ai_enabled=self.ai_ready
            editor.refactorRequested.connect(self.prepare_refactor)
            editor.definitionRequested.connect(self.go_to_definition)
            editor.formatRequested.connect(self.format_current)
        self.editor_tabs.setCurrentWidget(editor); self.editor_stack.setCurrentIndex(1)
        if line:editor.goto_line(line)
        editor.setFocus(); self.cursor_symbol(); self.refresh_actions()

    def mark_modified(self,editor,modified):
        document=self.documents.get(editor)
        if document:self.editor_tabs.setTabText(self.editor_tabs.indexOf(editor),document.path.name+(" •" if modified else ""))
        if modified and document and is_indexable(document.path):self.invalidate_results()

    def editor_changed(self,index):
        if hasattr(self,'find_panel') and self.find_panel.isVisible():self.find_panel.refresh()
        if hasattr(self,"breadcrumb"):
            editor=self.editor_tabs.widget(index); doc=self.documents.get(editor)
            self.breadcrumb.setText(str(doc.path.relative_to(Path(self.snapshot.root))).replace("\\","  /  ") if doc and self.snapshot else "")
        if not self.editor_tabs.count():self.editor_stack.setCurrentIndex(0)
        self.cursor_symbol(); self.refresh_actions()

    def close_document(self,index):
        editor=self.editor_tabs.widget(index); document=self.documents[editor]
        if editor.document().isModified():
            reply=QMessageBox.question(self,"Unsaved file",f"Save {document.path.name}?",QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
            if reply==QMessageBox.StandardButton.Cancel:return
            if reply==QMessageBox.StandardButton.Save and not self.save_editor(editor):return
        with paint_transaction(self):
            relative=document.path.relative_to(Path(self.snapshot.root)).as_posix(); self.documents.pop(editor); self.editors.pop(relative,None); self.editor_tabs.removeTab(index); editor.deleteLater()

    def save_editor(self,editor):
        try:
            if editor.document().isModified() and not editor.isReadOnly():
                if editor.toPlainText()!=self.documents[editor].text:self.documents[editor].save(editor.toPlainText())
                editor.document().setModified(False)
            return True
        except (OSError,ValueError,UnicodeError) as exc:self.notify(str(exc),True);return False

    def save_current(self):
        editor=self.current_editor()
        if editor and self.save_editor(editor):
            self.notify("Saved — project checks update automatically.")
            self.pending_check=True; self.check_timer.start()

    def format_current(self):
        if self.worker:return
        editor=self.current_editor();document=self.current_document()
        if not editor or not document:self.notify('Open a source document to format.',True);return
        if editor.isReadOnly():self.notify('This document is read-only. Open the editable sample or your own project.',True);return
        if not formatter_for(document.path):self.notify('Formatter available for Python, JS/JSX, TS/TSX, JSON/JSONC and Dart (installed SDK).',True);return
        source=editor.toPlainText();path=document.path
        def completed(result):
            if editor not in self.documents:self.notify('The formatted document was closed. Open it and format again.',True);return
            if not result['changed']:self.notify('Already formatted · '+result['engine']);return
            def apply():
                if editor not in self.documents or self.documents[editor].path!=path:raise ValueError('Workspace changed. Format the document again.')
                apply_to_editor(editor,result);self.editor_tabs.setCurrentWidget(editor);self.navigate(0)
                self.notify('Formatting applied to editor · Ctrl+Z to undo · Ctrl+S to save.')
            self.format_preview=FormatPreview(result,apply,self);self.format_preview.show()
        self.start(lambda cancel,progress:format_document(path,source,cancel),completed)

    def save_all(self):
        return all(self.save_editor(editor) for editor in list(self.documents))

    def find_in_file(self):
        if self.current_editor():self.navigate(0);self.find_panel.open()

    def find_next(self):
        self.find_panel.step(1)

    def search_project(self,query=''):
        if not self.snapshot:self.notify('Open a project before searching its files.',True);return
        from .find_ui import ProjectSearch
        self.project_search=ProjectSearch(self,query);self.project_search.show();self.project_search.query.setFocus()

    def cursor_symbol(self):
        editor=self.current_editor(); document=self.current_document()
        if not editor or not document or not self.snapshot:return
        path=document.path.relative_to(Path(self.snapshot.root)).as_posix(); line=editor.textCursor().blockNumber()+1
        file_key=(self.snapshot.id,path)
        if getattr(self,'_cursor_file_key',None)!=file_key:
            self._cursor_file_key=file_key
            self._cursor_file_symbols=[s for s in self.snapshot.symbols.values() if s.path==path]
        matches=[symbol for symbol in self._cursor_file_symbols if symbol.start<=line<=symbol.end]
        if hasattr(self,"outline") and getattr(self,"_outline_key",None)!=(self.snapshot.id,path):
            self._outline_key=(self.snapshot.id,path)
            self.outline.clear()
            for candidate in sorted((s for s in self._cursor_file_symbols if not s.is_test),key=lambda s:s.start):
                item=QListWidgetItem(candidate.qualname); item.setData(Qt.ItemDataRole.UserRole,candidate.id); self.outline.addItem(item)
        symbol=min(matches,key=lambda s:s.end-s.start) if matches else None
        context_key=(self.snapshot.id,path,symbol.id if symbol else None)
        if getattr(self,'_cursor_context_key',None)==context_key:
            self.update_refactor_context()
            return
        self._cursor_context_key=context_key
        if matches:
            index=self.symbols.findData(symbol.id)
            if index>=0:self.symbols.setCurrentIndex(index)
            self.symbol_info.setText(f"{symbol.kind.replace('_',' ')} · lines {symbol.start}–{symbol.end}\n{symbol.path}"); self.ideas.clear()
            if getattr(self,'_suggestions_snapshot',None)!=self.snapshot.id:
                self._suggestions_snapshot=self.snapshot.id;self._suggestions_cache={}
            if symbol.id not in self._suggestions_cache:self._suggestions_cache[symbol.id]=suggestions(symbol)
            for idea in self._suggestions_cache[symbol.id]:
                item=QListWidgetItem(idea["title"]); item.setToolTip(idea["reason"]); item.setData(Qt.ItemDataRole.UserRole,idea); self.ideas.addItem(item)
        else:self.symbol_info.clear();self.ideas.clear()
        self.update_refactor_context()

    def select_symbol(self,sid):
        symbol=self.snapshot.symbols.get(sid)
        if symbol:self.open_file(symbol.path,symbol.start)

    def request_completion(self,automatic=False):
        editor=self.current_editor(); document=self.current_document()
        if not editor or not document or document.path.suffix!=".py" or self.completion_worker is not None:return
        code=editor.toPlainText(); cursor=editor.textCursor(); position=cursor.position(); line=cursor.blockNumber()+1
        col=len(cursor.block().text().encode("utf-16-le")[:cursor.positionInBlock()*2].decode("utf-16-le"))
        worker=Worker(lambda cancel,progress:complete_python(code,str(document.path),line,col,self.snapshot.root),self); self.completion_worker=worker
        def complete(rows):
            if editor in self.documents and self.current_editor() is editor and editor.toPlainText()==code and editor.textCursor().position()==position:editor.offer_completions([row["name"] for row in rows],explicit=not automatic)
        worker.done.connect(complete); worker.failed.connect(lambda error:self.status.setText("Completion unavailable: "+error[:100]))
        worker.finished.connect(lambda:(setattr(self,"completion_worker",None),worker.deleteLater())); worker.start()

    def capture_baseline(self):
        if not self.snapshot or not self.save_all():return
        def task(cancel,progress):
            snapshot=index_repository(Path(self.snapshot.root),cancel,progress); capture_baseline(snapshot); return snapshot
        self.start(task,lambda snapshot:(self.indexed(snapshot,True),self.comparison.setCurrentIndex(self.comparison.findData("baseline")),self.notify("Comparison point updated. Checks refresh after saving."),self.check_timer.start()))

    def go_to_definition(self):
        editor=self.current_editor(); document=self.current_document()
        if not editor or not document:return
        if language_for(document.path)!="python":
            self.notify("Static definition navigation currently supports Python. Use the Lens evidence to open resolved dependencies.",True);return
        cursor=editor.textCursor(); line=cursor.blockNumber()+1
        col=len(cursor.block().text().encode("utf-16-le")[:cursor.positionInBlock()*2].decode("utf-16-le"))
        code=editor.toPlainText(); root=self.snapshot.root
        def done(rows):
            for row in rows:
                target=Path(row["path"]).resolve()
                if target.is_relative_to(Path(root)):
                    self.open_file(target.relative_to(Path(root)).as_posix(),row["line"]); self.navigate(0); return
            self.notify("No source definition was resolved inside this workspace.",True)
        self.start(lambda cancel,progress:find_definition(code,str(document.path),line,col,root),done)

    def model_path(self):
        path=app_dir()/"model.json"; return path if path.exists() else None

    def analyze_selected(self):
        editor=self.current_editor(); document=self.current_document()
        if self.snapshot and editor and document:
            self.analyze({"path":document.path.relative_to(Path(self.snapshot.root)).as_posix(),"line":editor.textCursor().blockNumber()+1})

    def analyze_changes(self):
        if self.snapshot:self.analyze(None)

    def analyze(self,seeds,run_after=False):
        if not self.save_all():return
        self.pending_check=False; self.check_timer.stop()
        root=Path(self.snapshot.root); mode=self.comparison.currentData(); model=self.model_path()
        def done(result):
            self.analyzed(result)
            if run_after and self.report["summary"]["recommended_tests"]:self.check_and_run()
        self.start(lambda cancel,progress:analyze_workspace(root,seeds,mode,model,cancel,progress),done)

    @atomic_paint
    def analyzed(self,result,show_review=True):
        self.snapshot,self.report=result; self.patch=None; report=self.report
        if not show_review:self.reload_clean_documents()
        self.report_stale=any(editor.document().isModified() and is_indexable(document.path) for editor,document in self.documents.items())
        self.patch_stale=False; self.test_choices.clear(); self.update_result_state()
        self.populate_symbols(); self.populate_explorer(); self.populate_diagnostics(); self.populate_tests()
        for key,widget in self.metrics.items():widget.setText(f"{report['summary'][key]:.2f}s" if key=="seconds" else str(report["summary"][key]))
        self.impact_summary.setText(f"{report['summary']['affected_symbols']} potentially affected symbols. Select a relationship to inspect its source and reasoning.")
        self.impact_view.clear(); nodes={}
        for row in sorted(report["impact"],key=lambda r:(r["distance"],r["symbol"])):
            sid=row["symbol"]; location=report["locations"].get(sid,{})
            relation="Changed / selected" if not row["distance"] else "Direct reference" if row["distance"]==1 else "Transitive reference"
            if any(edge["kind"] in INFERRED_KINDS for edge in row["evidence"]):relation="Inferred relationship"
            parent=nodes.get(row["path"][-2]) if len(row["path"])>1 else None
            item=QTreeWidgetItem(parent or self.impact_view,[sid.split(":",1)[-1],relation,f"{location.get('path','')}:{location.get('start','')}"])
            item.setIcon(0,icon("test" if location.get("is_test") else "code")); item.setData(0,Qt.ItemDataRole.UserRole,row); nodes[sid]=item
        self.impact_view.expandToDepth(1)
        if self.impact_view.topLevelItemCount():self.impact_clicked(self.impact_view.topLevelItem(0),0)
        self.change_rows=report["changes"]["files"]; self.change_list.clear()
        for row in self.change_rows:
            item=QListWidgetItem(icon("file"),Path(row["path"]).name+"\n"+row["status"]); item.setToolTip(row["path"]); self.change_list.addItem(item)
        self.change_summary.setText(f"{len(self.change_rows)} changed source/configuration files · Compared with {report['comparison']} · Saved edits included")
        if self.change_rows:self.change_list.setCurrentRow(0)
        else:self.changes_view.clear()
        self.populate_review(); self.update_watchers()
        if report["possible_gaps"]:self.notify(f"Check complete · {len(report['possible_gaps'])} symbols need a closer look in Review.")
        elif not report["changes"]["seeds"]:self.notify("Ready — edit and save; checks refresh automatically.")
        else:self.notify(f"Check complete · {report['summary']['recommended_tests']} recommended tests ready to run.")
        if show_review:self.navigate(6)

    def reload_clean_documents(self):
        for editor,document in list(self.documents.items()):
            if editor.document().isModified():continue
            if not document.path.exists():
                editor.setReadOnly(True); self.editor_tabs.setTabText(self.editor_tabs.indexOf(editor),document.path.name+" (deleted)"); continue
            fresh=Document(document.path)
            if fresh.digest!=document.digest:
                position=editor.textCursor().position(); self.documents[editor]=fresh; editor.set_code(fresh.text)
                cursor=editor.textCursor(); cursor.setPosition(min(position,editor.document().characterCount()-1)); editor.setTextCursor(cursor)
            editor.setReadOnly(Path(self.snapshot.root)==(resources()/"demo").resolve())

    def impact_clicked(self,item,column):
        row=item.data(0,Qt.ItemDataRole.UserRole)
        if not row:return
        self.evidence_sid=row["symbol"]; self.evidence_title.setText(row["symbol"].split(":",1)[-1]); reasons=[]
        for edge in row["evidence"]:
            relationship={"enclosing_scope":"contains nested code (inference)","inferred_method":"calls a method on an inferred receiver","fixture_dependency":"depends on fixture", "historical_reference":"previously referenced deleted code"}.get(edge["kind"],"references")
            reasons.append(f"{edge['caller']} {relationship} {edge['callee']} at line {edge['line']} ({edge['expression']}).")
        self.evidence_reason.setText("\n".join(reasons) or "This is the selected or changed symbol where impact tracing begins.")
        symbol=self.snapshot.symbols.get(row["symbol"])
        if symbol:self.source_view.set_language(symbol.path)
        self.source_view.set_code(symbol.source if symbol else "# This symbol was deleted.",symbol.start if symbol else 1)

    def open_evidence(self):
        if self.snapshot and getattr(self,"evidence_sid",None) in self.snapshot.symbols:self.select_symbol(self.evidence_sid); self.navigate(0)

    def show_change(self,index):
        if not 0<=index<len(self.change_rows):return
        row=self.change_rows[index]; before=row.get("before"); after=row.get("after")
        if before is None:
            root=Path(self.snapshot.root)
            try:prefix=git(root,"rev-parse","--show-prefix").strip(); before=git(root,"show",f"HEAD:{prefix}{row['path']}")
            except (ValueError,OSError):before=""
            target=root/row["path"]; after=decode_source(target.read_bytes()) if target.exists() else ""
        self.changes_view.set_versions(before,after,row["path"])

    def populate_tests(self):
        self.test_table.blockSignals(True)
        self.test_rows=[row for row in self.report["tests"] if self.show_weak.isChecked() or row["recommended"]] if self.report else []
        self.test_table.setRowCount(len(self.test_rows))
        for index,row in enumerate(self.test_rows):
            symbol=self.snapshot.symbols.get(row["symbol"]); name=(symbol.qualname+"\n"+symbol.path) if symbol else row["symbol"]
            for col,value in enumerate([name,row["relation"],f"{row['score']:.3f}"]):
                item=QTableWidgetItem(value); item.setToolTip(row["reason"]); self.test_table.setItem(index,col,item)
            check=QTableWidgetItem(); check.setFlags(Qt.ItemFlag.ItemIsUserCheckable|Qt.ItemFlag.ItemIsEnabled); check.setCheckState(Qt.CheckState.Checked if self.test_choices.get(row["symbol"],row["recommended"]) else Qt.CheckState.Unchecked); self.test_table.setItem(index,3,check); self.test_table.setRowHeight(index,52)
        self.test_table.blockSignals(False)
        if self.report:self.test_summary.setText(f"{sum(row['recommended'] for row in self.report['tests'])} linked · {len(self.report['tests'])} discovered · {self.report.get('ranking',{}).get('method','')} · scores order tests within evidence groups")
        self.refresh_actions()

    def test_choice_changed(self,item):
        if item.column()==3 and 0<=item.row()<len(self.test_rows):
            self.test_choices[self.test_rows[item.row()]["symbol"]]=item.checkState()==Qt.CheckState.Checked
            self.refresh_actions()

    def show_test_features(self,row,column):
        if 0<=row<len(self.test_rows):
            result=self.test_rows[row]; evidence="\n".join(f"{e['caller']} -> {e['callee']} · line {e['line']} · {e['expression']}" for e in result["evidence"])
            self.test_reason.setText(result["reason"]+("\n"+evidence if evidence else "")+"\n"+result.get("model_scope","")+"\nScores rank within evidence groups; they are not correctness probabilities.")

    def checked_tests(self):
        return [row["symbol"] for index,row in enumerate(self.test_rows) if self.test_table.item(index,3).checkState()==Qt.CheckState.Checked]

    def choose_interpreter(self):
        path,_=QFileDialog.getOpenFileName(self,"Choose Python, Node or Dart runtime",self.interpreter.text(),"Runtimes (python.exe node.exe dart.exe python node dart);;All files (*)")
        if path:self.interpreter.setText(path)

    def validate_demo(self,mutation=False):
        if not self.snapshot or not self.report or not self.save_all():return
        if self.report_stale or self.report["snapshot"]!=self.snapshot.id:
            self.notify("Analyze the saved source again before running these test recommendations.",True); return
        snapshot=self.snapshot; selected=self.checked_tests(); self.navigate(3)
        if not selected:self.notify("Check at least one test to run.",True);return
        if not execution_family(snapshot,selected):self.notify("Select Python, JavaScript/TypeScript or Flutter tests from one execution family. Other languages provide structural recommendations only.",True);return
        if Path(snapshot.root)==(resources()/"demo").resolve():
            task=lambda cancel,progress:execute_demo(Path(snapshot.root),[sid.replace(":","::",1) for sid in selected],None,mutation,cancel,progress)
        else:
            if mutation:self.notify("Fault injection is only available for the controlled demo.",True);return
            if snapshot.root not in self.trusted_roots:
                reply=QMessageBox.question(self,"Trust this repository for execution?","Running tests executes this project's code, dependencies and plugins on your laptop. Continue only if you trust its code. JS/TS selection uses files or framework path filters and may run other tests in those files.\n\n"+snapshot.root,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
                if reply!=QMessageBox.StandardButton.Yes:return
                self.trusted_roots.add(snapshot.root)
            interpreter=self.interpreter.text(); timeout=self.timeout.value()
            task=lambda cancel,progress:run_project_tests(snapshot,selected,interpreter,True,timeout,cancel,progress)
        self.validation_view.clear(); self.run_summary.setText("Running selected tests against saved source…"); self.start(task,self.validated,True)

    def validated(self,result):
        if "full" in result:
            selected,full=result["selected"],result["full"]; self.report["demo_validation"]=result
            self.run_summary.setText(f"Selected: {selected['status']} · Full demo: {full['status']} · {full['seconds']:.2f}s")
            output="SELECTED TESTS\n"+selected["output"]+"\nFULL DEMO SUITE\n"+full["output"]
            if result["controlled_mutation"]:output+="\nControlled fault: observed failing-test recall = "+str(result["failing_test_recall"])
        else:
            self.report["test_run"]=result; self.run_summary.setText(f"{result['status'].upper()} · {result['tests_requested']} {result.get('selection_unit','tests')} requested · {result['seconds']:.2f}s · {result['scope']}"); output=result["output"]
        self.validation_view.setPlainText(output); self.notify("Test run finished. Preview patches were not applied to the repository.")

    def update_refactor_context(self):
        if not hasattr(self,"refactor_context"):return
        if self.patch and self.patch["operation"]=="ai_rewrite" and self.operation.currentData()=="ai_rewrite":
            self.refactor_context.setText(self.patch.get("explanation","")+"\nGenerated locally · syntax checked · behavior not proven · tests not run")
            return
        editor=self.current_editor(); document=self.current_document()
        if not editor or not document:return
        if language_for(document.path)!="python":
            self.refactor_context.setText("Local AI suggested improvement supports this language with syntax and declaration checks. Structural rename/extract remains Python-only. Review every proposal; types, behavior and tests are not verified."); return
        cursor=editor.textCursor(); word=QTextCursor(cursor); word.select(QTextCursor.SelectionType.WordUnderCursor)
        selected=cursor.selectedText() if cursor.hasSelection() else word.selectedText()
        self.old_name.setText(selected if selected.isidentifier() else "(selection)" if cursor.hasSelection() else "")
        selection=f"{cursor.selectionEnd()-cursor.selectionStart()} characters selected" if cursor.hasSelection() else "cursor on "+(word.selectedText() or "no name")
        self.refactor_context.setText(f"{document.path.name} · line {cursor.blockNumber()+1} · {selection}")

    def prepare_rename(self):
        if self.current_document() and language_for(self.current_document().path)!="python":self.notify("Reviewed rename/extract currently supports Python only. Use the Brief for explanations of this language.",True); return
        if self.current_editor():
            self.patch=None; self.patch_list.clear(); self.diff_view.clear(); self.new_name.clear()
            self.operation.setCurrentIndex(0); self.update_refactor_context(); self.navigate(4); self.new_name.setFocus(); self.update_result_state()

    def refactor_mode_changed(self,*args):
        generated=self.operation.currentData()=="ai_rewrite"
        self.old_name.setVisible(not generated); self.new_name.setVisible(not generated)
        self.preview_button.setText("Regenerate suggestion" if generated else "Preview changes")
        self.refresh_actions()

    def prepare_refactor(self,operation):
        if self.current_document() and language_for(self.current_document().path)!="python":self.notify("Reviewed rename/extract currently supports Python only.",True); return
        self.patch=None; self.patch_list.clear(); self.diff_view.clear()
        self.operation.setCurrentIndex(self.operation.findData(operation)); self.update_refactor_context(); self.navigate(4); self.new_name.setFocus()
        if operation in {"extract_method","extract_variable"} and self.current_editor():
            import re
            names=set(re.findall(r"\w+",self.current_editor().toPlainText()))
            stem="extracted_helper" if operation=="extract_method" else "extracted_value"
            candidate=stem; number=2
            while candidate in names:candidate=f"{stem}_{number}"; number+=1
            self.new_name.setText(candidate); self.preview_timer.start()

    def idea_clicked(self,item):
        idea=item.data(Qt.ItemDataRole.UserRole); self.operation.setCurrentIndex(self.operation.findData(idea["operation"])); self.navigate(4); self.notify(idea["reason"])

    def preview(self):
        self.preview_timer.stop(); self.check_timer.stop(); self.pending_check=False
        if self.operation.currentData()=="ai_rewrite":self.suggest_rewrite(); return
        editor=self.current_editor(); document=self.current_document()
        if not editor or not document or not self.save_all():return
        cursor=editor.textCursor(); start=editor.code_offset(cursor.selectionStart() if cursor.hasSelection() else cursor.position()); end=editor.code_offset(cursor.selectionEnd()) if cursor.hasSelection() else None
        root=Path(self.snapshot.root); path=document.path.relative_to(root).as_posix(); operation=self.operation.currentData(); name=self.new_name.text().strip()
        if not name:self.notify("Enter a new name for the symbol, helper or variable.",True);return
        self.patch=None
        def task(cancel,progress):
            snapshot=index_repository(root,cancel,progress); return snapshot,preview_refactoring(snapshot,path,operation,name,start,end,cancel,progress)
        self.start(task,self.previewed)

    def previewed(self,result):
        self.snapshot,self.patch=result; self.patch_list.clear()
        self.report_stale=bool(self.report and self.report["snapshot"]!=self.snapshot.id) or any(editor.document().isModified() and is_indexable(document.path) for editor,document in self.documents.items())
        self.patch_stale=(self.patch["new"]!=self.new_name.text().strip() or self.patch["operation"]!=self.operation.currentData() or
            any(editor.document().isModified() and is_indexable(document.path) for editor,document in self.documents.items()))
        if self.patch_stale:self.preview_timer.start()
        self.update_result_state()
        for row in self.patch["files"]:self.patch_list.addItem(QListWidgetItem(icon("file"),row["path"]))
        self.patch_list.setCurrentRow(0); self.navigate(4); self.notify(f"Preview ready · {len(self.patch['files'])} files · syntax passed · tests not run. Original files unchanged.")
        if self.patch["operation"]=="ai_rewrite":self.refactor_context.setText(self.patch.get("explanation","")+"\nGenerated locally · syntax checked · behavior not proven · tests not run")

    def show_patch_file(self,index):
        if self.patch and 0<=index<len(self.patch["files"]):
            row=self.patch["files"][index]; self.diff_view.set_versions(row["before"],row["after"],row["path"])

    def apply_patch(self):
        if not self.patch or not self.save_all():return
        if self.patch["new"]!=self.new_name.text().strip() or self.patch["operation"]!=self.operation.currentData():
            self.notify("Wait for the updated preview before applying this refactoring.",True); return
        if Path(self.snapshot.root)==(resources()/"demo").resolve():
            self.notify("The bundled template is read-only. Open the sample project working copy to apply edits.",True);return
        snapshot,patch=self.snapshot,self.patch
        # Applying requires the explicit button after the user has seen the preview.
        def task(cancel,progress):
            checkpoint(cancel)
            result=apply_reviewed_patch(snapshot,patch)
            return index_repository(Path(snapshot.root),progress=progress),result
        def done(result):
            indexed,record=result
            self.snapshot=indexed; self.patch=None
            for editor,document in list(self.documents.items()):
                relative=document.path.relative_to(Path(indexed.root)).as_posix()
                if relative in record["files"]:
                    fresh=Document(document.path); self.documents[editor]=fresh; editor.set_code(fresh.text)
            self.populate_symbols(); self.populate_explorer(); self.notify(f"Applied {len(record['files'])} reviewed files. Backup: {record['backup']}")
            self.analyze_changes()
        self.start(task,done)
        self.cancel_button.hide()

    def populate_diagnostics(self):
        rows=self.report["warnings"] if self.report else self.snapshot.warnings if self.snapshot else []
        self.diagnostics.clear(); query=self.diagnostic_search.text().casefold()
        self.diagnostics.addItems([row for row in rows if query in row.casefold()]); count=sum(row.startswith(("Cannot parse","Skipped")) for row in rows)
        self.diagnostic_summary.setText(f"{count} file issues · {len(rows)-count} unresolved or conservative relationships. These are analysis limits, not confirmed defects.")
        if self.snapshot:
            profile=self.snapshot.profile
            for language,cap in profile.get("capabilities",{}).items():
                value=f"{cap['language']} ({profile['languages'][language]} files) · {cap['impact']} · tests: {cap['test_execution']} · AI rewrite: syntax/signature checked · structural rename/extract: {'available' if language=='python' else 'unavailable'}"
                if query in value.casefold():self.diagnostics.addItem(value)
            for framework in profile.get("frameworks",[]):
                value=f"Framework hint: {framework['name']} · {framework['path']} · {framework['evidence']} · {framework['note']}"
                if query in value.casefold():self.diagnostics.addItem(value)

    def train(self):
        def done(model):self.validation_view.setPlainText("Model retrained.\ntraining_pairs: "+str(model["training_pairs"])); self.notify("Experimental test ranker retrained from synthetic examples.")
        self.start(lambda cancel,progress:train_model(app_dir()/"model.json",cancel,progress),done)

    def export_report(self):
        if not self.report:return
        filename,_=QFileDialog.getSaveFileName(self,"Export analysis",str(app_dir()/"reports"/"analysis.json"),"JSON (*.json);;Markdown (*.md)")
        if filename:
            try:
                record={**self.report,"freshness":"out of date" if self.report_stale else "snapshot report; disk freshness not rechecked at export"}
                path=Path(filename); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(report_markdown(record) if path.suffix.lower()==".md" else json.dumps(record,indent=2),encoding="utf-8"); self.notify("Analysis exported.")
            except OSError as exc:self.notify(str(exc),True)

    def export_patch(self):
        if not self.patch:return
        if self.patch_stale:self.notify("Generate a fresh preview before exporting this refactoring.",True); return
        try:
            ensure_fresh(self.snapshot); filename,_=QFileDialog.getSaveFileName(self,"Export patch",str(app_dir()/"reports"/"refactoring.diff"),"Unified diff (*.diff)")
            if filename:
                path=Path(filename); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(self.patch["diff"],encoding="utf-8"); self.notify("Patch exported for review and application through version control.")
        except (OSError,ValueError) as exc:self.notify(str(exc),True)

    def closeEvent(self,event):
        from .find_ui import ProjectSearch
        for dialog in self.findChildren(ProjectSearch):
            if dialog.worker and dialog.worker.isRunning():dialog.close();self.notify('Stopping project search. Close again when it finishes.');event.ignore();return
        self.check_timer.stop(); self.preview_timer.stop(); self.pending_check=False
        self.pending_ai_completion=False
        if self.ai_worker:
            self.cancel_ai(); self.ai_worker.wait(2000)
            if self.ai_worker and self.ai_worker.isRunning():event.ignore(); return
        if self.worker:self.cancel(); self.notify("Cancelling work. Close again when it finishes."); event.ignore(); return
        if self.completion_worker:
            self.completion_worker.wait(2000)
            if self.completion_worker.isRunning():event.ignore(); return
        if not self.confirm_unsaved():event.ignore(); return
        paths=self.watcher.files()+self.watcher.directories()
        if paths:self.watcher.removePaths(paths)
        event.accept()


def main():
    app=QApplication(sys.argv); app.setApplicationName("Change Lens"); app.setOrganizationName("ChangeLens")
    window=MainWindow(); window.show()
    if "--demo" in sys.argv:window.open_path(resources()/"demo")
    sys.exit(app.exec())
