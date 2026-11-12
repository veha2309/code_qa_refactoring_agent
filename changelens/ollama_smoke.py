"""Native live-model workflow on disposable JS, TSX and Dart sources."""
import json
import os
import tempfile
import time
from pathlib import Path


def run(output):
    os.environ['CHANGELENS_TEST_NO_AI']='1'
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from .core import app_dir
    from .workbench import MainWindow
    app=QApplication.instance() or QApplication([]);temporary=tempfile.TemporaryDirectory(prefix='ollama-languages-',dir=app_dir());root=Path(temporary.name)
    cases=[('calc.js','JavaScript / JSX',"export function label(value) { if (value > 0) { return 'positive'; } else { return 'non-positive'; } }"),
        ('calc.tsx','TypeScript / TSX',"export function label(value: number): string { if (value > 0) { return 'positive'; } else { return 'non-positive'; } }"),
        ('calc.dart','Dart / Flutter',"String label(int value) { if (value > 0) { return 'positive'; } else { return 'non-positive'; } }")]
    for name,_,source in cases:(root/name).write_text(source,encoding='utf-8')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);checks=[];window=MainWindow();window.show();window.open_path(root);timer=QTimer();state=0;case=0;started=time.monotonic();phase_started=started
    def finish(error=None):
        timer.stop();output.write_text(json.dumps({'passed':error is None,'live_model':True,'model':window.local_ai.assistant_model,'checks':checks,'failures':[str(error)] if error else []},indent=2),encoding='utf-8')
        window.close();temporary.cleanup();app.exit(1 if error else 0)
    def tick():
        nonlocal state,case,phase_started
        try:
            if time.monotonic()-started>240:raise TimeoutError('Live Ollama UI workflow exceeded 240 seconds.')
            if window.worker or window.ai_worker or window.pending_model_action:return
            if state==0:
                name,language,_=cases[case];window.open_file(name,1);window.navigate(0);window.review_code();phase_started=time.monotonic();state=1;return
            if state==1:
                name,language,_=cases[case];review=getattr(window,'last_model_review',{})
                assert review.get('language')==language,(language,window.ai_status.text())
                assert window.assistant_ready and window.ai_ready,'Installed Ollama models were not connected by the requested action.'
                checks.append({'language':language,'action':'findings','seconds':round(time.monotonic()-phase_started,2),'model_response':json.loads(review['answer'])})
                window.model_instruction.setText('Simplify the if/else returns into a conditional expression.');window.suggest_rewrite();phase_started=time.monotonic();state=2;return
            if state==2:
                name,language,original=cases[case]
                assert window.patch and window.patch['syntax_validation']=='passed',(language,window.ai_status.text(),window.refactor_context.text())
                assert (root/name).read_text(encoding='utf-8')==original
                checks.append({'language':language,'action':'rewrite preview','seconds':round(time.monotonic()-phase_started,2),'syntax_validation':window.patch['syntax_validation'],'tests':'not run'})
                case+=1
                if case==len(cases):finish();return
                window.patch=None;state=0
        except Exception as exc:finish(exc)
    timer.timeout.connect(tick);timer.start(100);return app.exec()
