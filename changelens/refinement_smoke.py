"""Controlled native regression checks for import, graph, search and AI review."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import shutil

def run(output):
    with_ai='--with-local-ai' in sys.argv
    if not with_ai:os.environ['CHANGELENS_TEST_NO_AI']='1'
    from PySide6.QtCore import QTimer,Qt
    from PySide6.QtGui import QTextCursor
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from .core import app_dir,index_repository
    from .local_ai import rewrite_patch
    from .workbench import MainWindow
    from .widgets import CodeEditor
    a=QApplication.instance() or QApplication([]);directory=tempfile.TemporaryDirectory(prefix='workflow-smoke-',dir=app_dir());root=Path(directory.name)
    sources={'AuthCard.tsx':'export function AuthCard(){return <div/>;}',
        'Login.tsx':"import {AuthCard} from './AuthCard';export function Login(){return <AuthCard/>;}",
        'Register.tsx':"import {AuthCard} from './AuthCard';export function Register(){return <AuthCard/>;}",
        'App.tsx':"import {Login} from './Login';import {Register} from './Register';export function App(){return <><Login/><Register/></>;}",
        'calc.ts':'export function total(n: number): number { const result = n + 1; return result; }\n',
        'service.py':'class Service:\n    def run(self):\n        value = """text\nflush left string\n        """\n        return value\n',
        '.python-packages/broken.py':'def broken(\n'}
    for name,source in sources.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(source,encoding='utf-8')
    from .ranking import resources
    shutil.copytree(resources()/'flutter_demo',root/'flutter',dirs_exist_ok=True)
    output.parent.mkdir(parents=True,exist_ok=True);window=MainWindow();window.show();checks=[];stage=0;timer=QTimer();started=time.monotonic()
    def finish(error=None):
        timer.stop();output.write_text(json.dumps({'passed':not error,'checks':checks,'failures':[str(error)] if error else [],'with_local_ai':with_ai},indent=2),encoding='utf-8')
        if window.worker:window.cancel()
        elif window.ai_worker:window.cancel_ai()
        else:window.close()
        a.exit(1 if error else 0)
    def tick():
        nonlocal stage
        if time.monotonic()-started>150:finish('Timed out');return
        if window.worker or window.ai_worker:return
        if window._pending_error:finish(window._pending_error);return
        try:
            if stage==0:
                snap=index_repository(root);assert 'service.py:Service.run' in snap.symbols
                assert not any('.python-packages' in path for path in snap.hashes);checks.append('valid indented method and excluded Python dependency folder')
                from .core import impact_paths
                flutter_rows=impact_paths(snap,['flutter/lib/auth_card.dart:AuthCard']);flutter_ids={row['symbol'] for row in flutter_rows}
                assert 'flutter/lib/main.dart:DemoApp' in flutter_ids
                assert sum(s.is_test and s.id in flutter_ids for s in snap.symbols.values())==2;checks.append('bundled Dart grammar, Flutter composition and widget test discovery')
                from .flutter_sdk import detect_sdk
                if detect_sdk():
                    from .formatting import format_document
                    formatted=format_document('check.dart','int total(int n){return n+1;}');assert 'return n + 1;' in formatted['after'];checks.append('installed Dart SDK formatter')
                else:checks.append('Dart SDK formatting skipped: optional SDK absent')
                patch=rewrite_patch(snap,snap.symbols['calc.ts:total'],json.dumps({'code':'function total(n: number): number { return n + 1; }'}))
                assert patch['files'][0]['after'].startswith('export function');assert (root/'calc.ts').read_text(encoding='utf-8')==sources['calc.ts'];checks.append('TypeScript exact-span checked proposal preserves export')
                window.open_path(root)
            elif stage==1:window.analyze(['AuthCard.tsx:AuthCard'])
            elif stage==2:
                view=window.lens_view;assert len(view.map.edges)==4;view.map.select_node('App.tsx:App');assert all(node.opacity()==1 for node in view.map.nodes.values());checks.append('both shared-component routes into App visible and highlighted')
                window.pages.finish_transition();window.grab().save(str(output.with_name(output.stem+'_graph.png')))
                window.open_file('App.tsx');window.navigate(0);window.find_in_file();window.find_bar.setText('AuthCard');window.find_panel.refresh();assert 'No matches' in window.find_panel.count.text();checks.append('file search shows no-match result')
                window.search_project('AuthCard');window.project_search.timer.stop();window.project_search.run()
            elif stage==3:
                if window.project_search.worker:return
                assert window.project_search.results.topLevelItemCount()>=5;checks.append('project search displays file/line matches')
                window.project_search.grab().save(str(output.with_name(output.stem+'_search.png')));window.project_search.close();window.find_panel.dismiss()
                editor=CodeEditor();editor.set_language('a.tsx');editor.set_code('function f() {}');cursor=editor.textCursor();cursor.setPosition(14);editor.setTextCursor(cursor);QTest.keyClick(editor,Qt.Key.Key_Return);assert editor.toPlainText()=='function f() {\n  \n}';editor.close();checks.append('native TS indentation and brace newline')
                window.navigate(6);window.navigate(0);assert window.pages.overlay is None and window.nav.marker is not None;checks.append('stable page switch with isolated navigation motion')
                if not with_ai:finish();return
                window.open_file('calc.ts');window.connect_ai()
            elif stage==4:
                assert window.assistant_ready;window.suggest_rewrite()
            elif stage==5:
                assert window.patch and window.patch['path']=='calc.ts' or 'No new improvement returned' in window.ai_status.text(),window.ai_status.text()
                assert window.preview_button.isEnabled();checks.append('actual local-model TypeScript checked proposal' if window.patch else 'actual local-model TypeScript explicit no-change response')
                window.preview()
            elif stage==6:
                assert window.patch and window.patch['path']=='calc.ts' or 'No new improvement returned' in window.ai_status.text(),window.ai_status.text()
                assert (root/'calc.ts').read_text(encoding='utf-8')==sources['calc.ts'];checks.append('actual TypeScript regeneration leaves source unchanged')
                checks.append('AI response: checked proposal' if window.patch else 'AI response: explicit no-change state; regeneration remains available')
                window.pages.finish_transition();window.grab().save(str(output.with_name(output.stem+'_ai.png')));finish();return
            stage+=1
        except Exception as exc:finish(repr(exc))
    timer.timeout.connect(tick);timer.start(100)
    return a.exec()
