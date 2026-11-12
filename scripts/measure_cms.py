"""Read-only CMS analysis and native UI timing; never execute target code."""
import argparse
import json
import platform
import time
from pathlib import Path
from changelens.core import index_repository
from changelens.feature_flows import analyze_flows


def measure(root,ui=False):
    result={'machine':platform.node(),'platform':platform.platform(),'note':'Measured on this computer; no repository code, tests or HTTP requests executed.'}
    start=time.perf_counter();snapshot=index_repository(root);result['index_seconds']=time.perf_counter()-start
    for label in ('cold','warm'):
        start=time.perf_counter()
        if ui:
            from PySide6.QtWidgets import QApplication
            from changelens.workbench import Worker
            app=QApplication.instance() or QApplication([]);values=[];errors=[];intervals=[]
            worker=Worker(lambda cancel,progress:analyze_flows(snapshot,cancel,progress));worker.done.connect(values.append);worker.failed.connect(errors.append);worker.start()
            last=time.perf_counter()
            while worker.isRunning():
                app.processEvents();now=time.perf_counter();intervals.append((now-last)*1000);last=now;time.sleep(.002)
            app.processEvents()
            if errors:raise RuntimeError(errors[0])
            analysis=values[0];result[label+'_worker_event_interval_ms']=max(intervals,default=0)
        else:analysis=analyze_flows(snapshot)
        result[label+'_flow_seconds']=time.perf_counter()-start;result[label+'_cache_hits']=analysis['cache_hits']
    result['summary']=analysis['summary'];result['files']=len(snapshot.hashes)
    calendar=[f for f in analysis['flows'] if f['path'].endswith('academic-cms/components/AcademicCalenderlist.js')]
    result['calendar']=[{'path':f['path'],'line':f['line'],'method':f['method'],'url':f['url'],'screen':f['screen'],
        'steps':f['steps'],'relationships':f['relationships'],'gaps':f['gaps'],
        'handlers':[{'path':m['handler_detail']['path'],'line':m['handler_detail']['line'],'name':m['handler_detail']['name'],
            'data':m['handler_detail']['data'],'responses':m['handler_detail']['responses']} for m in f['matches'] if m['handler_detail']],
        'updates':f['updates']} for f in calendar]
    if ui:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTimer
        from changelens.flow_ui import FeatureFlows
        app=QApplication.instance() or QApplication([]);view=FeatureFlows();view.resize(1400,850);view.show();app.processEvents()
        report={'project':str(root),'snapshot_id':snapshot.id,'feature_flows':analysis}
        intervals=[];last=[time.perf_counter()]
        def tick():
            now=time.perf_counter();intervals.append((now-last[0])*1000);last[0]=now
        timer=QTimer();timer.setInterval(10);timer.timeout.connect(tick);timer.start()
        start=time.perf_counter();view.set_report(report);app.processEvents();result['feature_view_ms']=(time.perf_counter()-start)*1000
        timings=[]
        for f in (calendar[:1] or analysis['flows'][:1]):
            for operation in (lambda:view.open_flow(f),view.show_detail,lambda:view.travel(-1),lambda:view.travel(1),view.show_systems):
                start=time.perf_counter();operation();app.processEvents();timings.append((time.perf_counter()-start)*1000)
        result['navigation_ms']=timings
        result['max_main_thread_operation_ms']=max([result['feature_view_ms']]+timings)
        # Observe a warm extraction in a worker while the native event loop runs.
        from changelens.workbench import Worker
        intervals.clear();last[0]=time.perf_counter()
        worker=Worker(lambda cancel,progress:analyze_flows(snapshot,cancel,progress))
        errors=[];worker.failed.connect(errors.append);worker.start()
        while worker.isRunning():app.processEvents();time.sleep(.002)
        app.processEvents();timer.stop();result['max_event_interval_ms']=max(intervals,default=0);result['worker_errors']=errors
        result['ui_targets_met']=max(timings,default=0)<100 and max(result['max_event_interval_ms'],result['max_main_thread_operation_ms'],result['cold_worker_event_interval_ms'],result['warm_worker_event_interval_ms'])<500
        view.close();app.processEvents()
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('project',type=Path);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--ui',action='store_true');args=parser.parse_args()
    result=measure(args.project.resolve(),args.ui);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='calendar'},indent=2))


if __name__=='__main__':main()
