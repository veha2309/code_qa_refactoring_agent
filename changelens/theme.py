"""Restrained native chrome, readable code and a single muted accent."""
COLORS = {"editor":"#191e25", "surface":"#1b2a31", "border":"#34474e",
          "text":"#d1dfe0", "muted":"#95aeb3", "selection":"#28443f"}

STYLESHEET = r'''
QMainWindow { background:#171b21; }
QDialog,QMessageBox { background:#20262e; }
QWidget { color:#c5d4d8; font-family:"Noto Sans"; font-size:13px; }
QLabel { background:transparent; }
QFrame#topbar { background:#20262e; border:1px solid rgba(183,222,220,35); border-top-color:rgba(204,239,232,65); border-radius:6px; }
QFrame#sidebar { background:rgba(19,31,38,185); border:1px solid rgba(185,219,218,24); border-radius:6px; }
QFrame#footer { background:transparent; border:none; }
QLabel#brand,QLabel#projectTitle { color:#d9e8e6; font-weight:500; padding:2px 6px; }
QLabel#identity { color:#a9dece; font-size:11px; font-weight:600; padding-right:10px; }
QLabel#pageTitle,QLabel#sectionTitle { color:#e2eae8; font-size:13px; font-weight:500; }
QLabel#eyebrow { color:#91aaa9; font-size:10px; padding:4px 0; }
QLabel#muted { color:#94abb3; }
QLabel#banner { color:#f1ccab; background:rgba(110,76,47,50); border:1px solid rgba(224,167,112,55); border-radius:4px; padding:9px 14px; }
QLabel#badge,QLabel#breadcrumb { color:#94b6b0; background:transparent; padding:4px 12px; }
QLabel#hero,QLabel#emptyTitle { color:#d5e6e0; font-size:26px; padding-bottom:12px; font-weight:400; }
QLabel#welcomeText { color:#9aafb4; padding-bottom:18px; }
QFrame#welcome { background:transparent; border:none; }
QFrame#inspector,QFrame#lensEvidence { background:rgba(26,42,48,225); border:1px solid rgba(172,211,208,36); border-top-color:rgba(203,232,226,60); border-radius:6px; }
QFrame#metricCard { background:rgba(34,51,58,130); border:1px solid rgba(175,211,205,24); border-radius:5px; }
QLabel#metricValue { color:#c6e4d8; font-size:20px; }
QPushButton,QPushButton#primary { background:rgba(61,84,89,90); color:#d6e5e3; border:1px solid rgba(180,217,210,48); border-radius:4px; padding:7px 12px; }
QPushButton:hover,QPushButton#primary:hover { background:rgba(96,143,139,60); border-color:rgba(171,224,207,110); }
QPushButton:pressed { background:rgba(104,162,145,85); }
QPushButton:disabled,QPushButton#primary:disabled { color:#6d858b; background:rgba(24,38,45,90); border-color:rgba(154,186,189,16); }
QPushButton:focus { border-color:#95c8b6; }
QPushButton#smallButton { background:transparent; border:1px solid transparent; color:#a5bbb9; padding:5px 8px; }
QPushButton#smallButton:hover { background:rgba(118,164,154,35); border-color:rgba(170,213,202,40); }
QPushButton#commandSearch { text-align:left; color:#98afb5; background:rgba(10,22,28,115); border:1px solid rgba(180,215,210,29); padding:6px 12px; }
QPushButton#lensAction { background:#304a45; border:1px solid rgba(167,219,191,90); color:#d5eddb; }
QPushButton#lensAction:hover { background:rgba(114,181,149,75); border-color:#a3d1b9; }
QPushButton#lensAction:disabled { color:#6d8580; background:rgba(24,38,45,90); border-color:rgba(154,186,189,16); }
QLineEdit,QComboBox,QSpinBox { background:rgba(13,27,34,170); border:1px solid rgba(176,206,211,42); border-radius:7px; padding:6px 9px; selection-background-color:#34564f; }
QLineEdit:focus,QComboBox:focus,QSpinBox:focus { border-color:#7fb3a4; }
QComboBox::drop-down { border:none; width:18px; }
QAbstractItemView { background:rgba(18,30,37,200); alternate-background-color:rgba(33,50,57,160); border:1px solid rgba(165,198,205,26); border-radius:4px; selection-background-color:#29443f; selection-color:#e4f1eb; outline:none; }
QAbstractItemView::item { padding:7px 6px; border:none; }
QTreeWidget#explorer { background:transparent; border:none; }
QTreeWidget#explorer::item { color:#a6bcc0; padding:5px 3px; }
QTreeWidget#explorer::item:selected { background:rgba(106,160,144,35); color:#d9e8e0; border-radius:6px; }
QListWidget#navigation { background:rgba(22,36,43,200); border:1px solid rgba(175,211,207,30); border-radius:5px; padding:3px; }
QListWidget#navigation::item { color:#9eb4b9; padding:4px 12px; margin:0 2px; border:1px solid transparent; border-radius:7px; }
QListWidget#navigation::item:hover { background:rgba(120,162,158,25); }
QListWidget#navigation::item:selected { color:#d7ecdf; background:rgba(107,170,144,35); border:1px solid rgba(151,207,177,60); }
QListWidget#outline,QListWidget#ideas { background:transparent; border:none; }
QHeaderView::section { background:#1c2c34; color:#a9c0c4; padding:9px; border:none; border-bottom:1px solid #34464c; }
QPlainTextEdit { background:#191e25; color:#d2dfe1; border:1px solid rgba(163,196,202,22); border-radius:4px; padding:10px 12px; font-family:"Roboto Mono"; font-size:14px; selection-background-color:#33574f; }
QPlainTextEdit#terminal { background:#101b20; color:#bfd9cb; }
QTabWidget::pane { border:none; }
QTabBar::tab { background:rgba(17,29,36,130); color:#90a9b1; padding:9px 18px; border:1px solid transparent; border-top-left-radius:8px; border-top-right-radius:8px; }
QTabBar::tab:selected { background:#191e25; color:#d4e8df; border:1px solid rgba(170,214,198,30); border-bottom:none; }
QSplitter::handle { background:transparent; width:6px; height:6px; }
QScrollBar:vertical { width:9px; background:transparent; }
QScrollBar:horizontal { height:9px; background:transparent; }
QScrollBar::handle:vertical,QScrollBar::handle:horizontal { background:rgba(147,183,183,75); min-height:26px; min-width:26px; border-radius:4px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal { width:0; }
QScrollBar::add-page,QScrollBar::sub-page { background:transparent; }
QProgressBar { background:#263c42; border:none; border-radius:3px; height:4px; }
QProgressBar::chunk { background:#a8d3bf; border-radius:3px; }
QMenuBar { background:#171b21; color:#9eb7b9; padding:2px 10px; font-size:11px; }
QMenuBar::item:selected { background:#29443f; border-radius:4px; }
QMenu { background:#1b2c34; border:1px solid #445c61; padding:6px; }
QMenu::item { padding:7px 20px; border-radius:5px; }
QMenu::item:selected { background:#304e47; }
QToolTip { background:#233a40; color:#dae8e5; border:1px solid #53736d; padding:6px; }
QDialog#commandPicker,QDialog#formatPreview { background:#20262e; border:1px solid #48635f; }
QDialog#commandPicker QLineEdit { border:none; padding:14px; background:transparent; font-size:14px; }
QDialog#commandPicker QListWidget { border:none; background:transparent; }
QLabel#lensTitle { color:#dfebe4; font-size:25px; font-weight:400; padding:3px 0 8px 0; }
QPlainTextEdit#lensReason { background:transparent; border:none; padding:0; font-family:"Noto Sans"; font-size:13px; color:#b2ccce; }
QGraphicsView#impactMap { border:1px solid rgba(169,212,204,38); border-radius:6px; background:#1b2129; }
QLabel#briefContext { color:#bbddd1; background:rgba(78,116,104,30); border:1px solid rgba(166,213,190,28); border-radius:4px; padding:10px 14px; }
QTextBrowser#briefView { background:rgba(21,36,43,205); color:#d2e0df; border:1px solid rgba(178,211,206,27); border-radius:6px; padding:20px 28px; font-family:"Noto Sans"; font-size:14px; selection-background-color:#34574f; }
QFrame#modelSettings { background:rgba(27,43,49,220); border:1px solid #3e5759; border-radius:5px; }
'''

# Compact controls keep attention on documents and evidence.
STYLESHEET += r'''
QListWidget#navigation { background:transparent; border:none; border-bottom:1px solid #303841; border-radius:0; padding:0; }
QListWidget#navigation::item { padding:3px 10px; margin:0 3px; border:none; border-radius:3px; }
QListWidget#navigation::item:selected { background:#2a353b; color:#e0ebe7; border:none; }
QFrame#sidebar { background:#1b2129; border:1px solid #2b333d; border-radius:4px; }
QLabel#breadcrumb { color:#94a2af; padding:7px 14px; font-size:11px; }
QLabel#identity { color:#cbdcd6; font-size:13px; font-weight:600; }
QPushButton { padding:6px 11px; }
QPlainTextEdit { padding:8px 10px; }
QTabBar::tab { padding:8px 14px; border-radius:0; }
QTabBar::tab:selected { border:0; border-bottom:2px solid #91b9aa; background:#191e25; }
QToolTip { font-size:12px; }
'''

STYLESHEET += r'''
QToolButton { background:transparent; color:#bfd0ce; border:1px solid #35424c; border-radius:4px; padding:4px 12px; }
QToolButton:hover { background:#29343d; border-color:#789b90; }
QToolButton::menu-indicator { image:none; }
'''

STYLESHEET += 'QToolButton:checked { background:#30463f; color:#e3eee7; border-color:#6d9988; }'
