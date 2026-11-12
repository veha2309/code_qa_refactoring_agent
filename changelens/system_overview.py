"""Language-independent, evidence-backed module and route overview."""
from collections import defaultdict
from pathlib import PurePosixPath
from .languages import NAMES


def overview_model(report):
    modules=report.get('modules',[]);groups=defaultdict(list)
    for module in modules:groups[str(PurePosixPath(module['path']).parent)].append(module)
    dependencies=report.get('dependencies',[]);weight=defaultdict(int)
    for edge in dependencies:
        weight[str(PurePosixPath(edge['from']).parent)]+=1;weight[str(PurePosixPath(edge['to']).parent)]+=1
    chosen=sorted(groups,key=lambda key:(-weight[key],key))[:40];nodes=[];edges=[]
    for i,key in enumerate(chosen):
        rows=groups[key];languages=sorted({NAMES.get(m['language'],m['language']) for m in rows})
        nodes.append({'id':'module:'+key,'title':key if key!='.' else report['project'],'kind':'Source modules','path':rows[0]['path'],'line':1,
            'fields':[],'operations':[str(len(rows))+' indexed files',', '.join(languages)]+[m['path'] for m in rows[:4]],'origin':'extracted','x':i%4*460,'y':i//4*340})
    joined=defaultdict(list)
    for dependency in dependencies:
        a=str(PurePosixPath(dependency['from']).parent);b=str(PurePosixPath(dependency['to']).parent)
        if a!=b and a in chosen and b in chosen:joined[a,b].append(dependency)
    for (a,b),rows in joined.items():
        evidence=[e for row in rows for e in row['evidence']]
        edges.append({'id':'dependency:'+a+':'+b,'from':'module:'+a,'to':'module:'+b,'label':str(len(rows))+' file dependencies',
            'classification':'resolved static' if any(r['classification']=='resolved static' for r in rows) else 'inferred','origin':'extracted','evidence':evidence})
    routes=report.get('feature_flows',{}).get('routes',[]);servers=defaultdict(list)
    for route in routes:servers[route['path']].append(route)
    start=(len(nodes)+3)//4
    for i,(path,rows) in enumerate(sorted(servers.items())[:12]):
        key='routes:'+path
        nodes.append({'id':key,'title':PurePosixPath(path).name,'kind':'Registered HTTP routes','path':path,'line':rows[0]['line'],'fields':[],
            'operations':[rows[0].get('framework','Express')]+[r['method']+' '+r['endpoint'] for r in rows[:6]]+(['More routes in report.json'] if len(rows)>6 else []),
            'origin':'extracted','x':i%4*460,'y':(start+i//4)*340})
        parent=str(PurePosixPath(path).parent)
        if parent in chosen:edges.append({'id':'register:'+key,'from':'module:'+parent,'to':key,'label':'registers routes','classification':'resolved static','origin':'extracted',
            'evidence':[{'path':r['path'],'line':r['line'],'expression':r['method']+' '+r['endpoint']} for r in rows]})
    omitted=max(0,len(groups)-40)+max(0,len(servers)-12)
    if not nodes or omitted:
        nodes.append({'id':'coverage','title':str(omitted)+' groups beyond preview' if nodes else 'No indexed source available','kind':'Analysis coverage','path':'','line':1,'fields':[],
            'operations':['Full indexed module/dependency records remain in report.json.','Detailed functional tracing depends on explicit framework adapters; no behavior was invented.'],
            'origin':'extracted','x':0,'y':((len(nodes)+3)//4)*340})
    from .design_canvas import node_height
    bottoms={}
    for node in sorted(nodes,key=lambda r:(r['x'],r['y'])):
        node['y']=max(node['y'],bottoms.get(node['x'],0));bottoms[node['x']]=node['y']+node_height(node)+70
    return {'format':'changelens-design','version':1,'snapshot_id':report['snapshot_id'],'project':report['project'],'level':'HLD','scope':'systems','page':0,'nodes':nodes,'edges':edges,
        'notice':'Source module overview for every indexed language. Folder grouping is structural; registered routes are source facts, not proof of runtime traffic. Draft edits change the diagram only.'}
