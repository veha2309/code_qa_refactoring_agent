"""Readable architecture review backed by witnesses, not raw warning volume."""
from collections import Counter,defaultdict,deque
from pathlib import PurePosixPath
import re
from .core import checkpoint

REFERENCE=re.compile(r'^Unresolved call(?:/reference)? (.+?):(\d+): (.*?)(?: \((?:external|dynamic).*)?$',re.S)
LOCAL_IMPORT=re.compile(r'^Unresolved local module (.+) imported by (.+)$')
RESOURCES={'.css','.scss','.sass','.less','.svg','.png','.jpg','.jpeg','.gif','.webp','.ico','.ttf','.woff','.woff2','.glb','.gltf','.mp4','.json','.yaml','.yml','.xml','.wasm'}
GLOBALS={'console','Math','JSON','Object','Array','String','Number','Boolean','Date','Promise','Map','Set','RegExp','Error','parseInt','parseFloat','isNaN','setTimeout','clearTimeout','setInterval','clearInterval','fetch','window','document','navigator','localStorage','sessionStorage','URL','Buffer','process'}


def diagnostic_digest(warnings,cancel=None):
    counts=Counter();groups={};files=defaultdict(set)
    for i,message in enumerate(warnings):
        if i%512==0:checkpoint(cancel)
        path='';line=1;expression='';match=REFERENCE.match(message)
        if match:
            path,line,expression=match.groups();line=int(line);receiver=expression.split('.',1)[0]
            category='global-shaped references' if receiver in GLOBALS else 'dynamic / external references'
            title=expression[:160];key=(category,title)
        elif message.startswith('Cannot parse '):
            category='parser exclusions';path=message[len('Cannot parse '):].split(': ',1)[0];title=path;key=(category,path)
            location=re.search(r'\b(?:near line|line) (\d+)\b',message)
            if location:line=int(location.group(1))
        elif message.startswith('Skipped '):
            category='skipped files';path=message[len('Skipped '):].split(': ',1)[0];title=path;key=(category,path)
        elif (local:=LOCAL_IMPORT.match(message)):
            spec,path=local.groups();category='non-source resource imports' if PurePosixPath(spec.split('?',1)[0]).suffix.lower() in RESOURCES else 'unresolved local imports'
            location=re.match(r'^(.*?):(\d+)$',path)
            if location:path,line=location.group(1),int(location.group(2))
            title=spec;key=(category,path,spec)
        elif message.startswith('Ambiguous'):
            category='ambiguous bindings';title=message[:160];key=(category,title)
        else:category='other analysis notes';title=message[:160];key=(category,title)
        counts[category]+=1
        if path:files[category].add(path)
        group=groups.setdefault(key,{'category':category,'title':title,'count':0,'examples':[],'files':set()})
        group['count']+=1
        if path:group['files'].add(path)
        if len(group['examples'])<3:group['examples'].append({'path':path,'line':line,'message':message[:700]})
    ordered=[]
    priority={'parser exclusions':0,'skipped files':1,'unresolved local imports':2,'ambiguous bindings':3}
    for group in groups.values():
        group['file_count']=len(group.pop('files'));ordered.append(group)
    ordered.sort(key=lambda g:(priority.get(g['category'],5),-g['count'],g['title']))
    return {'raw_occurrences':len(warnings),'counts':dict(counts),'file_counts':{k:len(v) for k,v in files.items()},
        'groups':ordered,'limitations':'Grouping describes analyzer coverage. Unresolved references and resource imports are not confirmed code defects.'}


def cycle_witness(members,dependencies,cancel=None):
    """One concrete closed path, with a source anchor for each directed edge."""
    members=set(members);adj=defaultdict(list);by_pair={}
    for edge in dependencies:
        if edge['classification']!='resolved static' or edge['from'] not in members or edge['to'] not in members:continue
        adj[edge['from']].append(edge['to']);by_pair[(edge['from'],edge['to'])]=edge
    if not members:return []
    start=min(members);queue=deque([start]);previous={start:None};end=None
    while queue and end is None:
        checkpoint(cancel);current=queue.popleft()
        for nxt in sorted(adj[current]):
            if nxt==start and current!=start:end=current;break
            if nxt not in previous:previous[nxt]=current;queue.append(nxt)
    if end is None:return []
    chain=[end]
    while chain[-1]!=start:chain.append(previous[chain[-1]])
    chain.reverse();chain.append(start);result=[]
    for a,b in zip(chain,chain[1:]):
        edge=by_pair[a,b]
        evidence=[e for e in edge['evidence'] if e['classification']=='resolved static']
        # Import-only evidence describes initialization dependencies directly.
        source=min(evidence,key=lambda e:(e['kind'] not in {'module_import','python_module_import'},e['line']))
        result.append({'from':a,'to':b,'path':source['path'],'line':source['line'],'expression':source['expression'],'kind':source['kind']})
    return result


def build_review(report,cancel=None):
    digest=diagnostic_digest(report['warnings'],cancel);items=[]
    for category,title in [('parser exclusions','Source files could not be indexed'),('skipped files','Source files excluded by size / access'),('unresolved local imports','Local code imports need verification')]:
        rows=[g for g in digest['groups'] if g['category']==category]
        if not rows:continue
        evidence=[e for row in rows for e in row['examples']]
        items.append({'kind':'coverage_gap','priority':'Coverage','title':f'{title}: {len(rows)}',
            'explanation':'These gaps can hide components and relationships. They describe incomplete analysis, not proof the project fails to build.',
            'next_step':'Open the source location, check language / import configuration and compare with the project compiler. Re-run the review after resolving the analysis gap.',
            'evidence':evidence,'locations':sorted({e['path'] for e in evidence if e['path']})})
    for finding in report['findings']:
        checkpoint(cancel)
        if finding['kind']!='dependency_cycle':continue
        witness=cycle_witness(finding['locations'],report['dependencies'],cancel)
        if not witness:continue
        entry=next((p for p in finding['locations'] if PurePosixPath(p).name in {'app.js','app.ts','server.js','server.ts','main.py','__main__.py'}),None)
        title=('Application entry participates in an import/reference cycle' if entry else 'Closed dependency path')+f' · {len(finding["locations"])} files in this component'
        items.append({'kind':'dependency_cycle','priority':'Review','title':title,
            'explanation':'The recorded graph contains a closed path: '+' → '.join([witness[0]['from']]+[e['to'] for e in witness])+'. This is a static initialization/reference concern; no runtime failure was observed.',
            'next_step':('Inspect imports back into '+entry+'. Check which shared export the consumer needs; consider moving that shared value into a separate module used by both sides, then verify initialization behavior.' if entry else 'Open each reference in this witness. Check initialization order and whether shared state or types can move into a common dependency. A cycle can be intentional; verify before changing code.'),
            'evidence':witness,'locations':finding['locations']})
    metrics=Counter(f['kind'] for f in report['findings'])
    systems=defaultdict(list)
    for flow in report.get('feature_flows',{}).get('flows',[]):systems[flow['app']].append(flow)
    system_rows=[]
    for app,flows in sorted(systems.items()):
        linked=sum(f['status']=='path match' for f in flows);ambiguous=sum(f['status']=='ambiguous' for f in flows)
        representative=sorted(flows,key=lambda f:(f['status']!='path match',not any((m['handler_detail'] or {}).get('data') for m in f['matches']),not bool(f['updates']),f['title']))[0]
        system_rows.append({'name':app,'kind':flows[0].get('consumer_kind','HTTP consumer'),'requests':len(flows),
            'unique_path_candidates':linked,'ambiguous':ambiguous,'unlinked':len(flows)-linked-ambiguous,'example_id':representative['id'],
            'example_title':representative['title'],'example_path':representative['path'],'example_line':representative['line']})
    return {'version':1,'items':items,'coverage':digest,'systems':system_rows,
        'metrics':{'large_definitions':metrics['large_definition'],'coupled_files':metrics['coupling'],'dependency_components':metrics['dependency_cycle'],
            'raw_heuristic_candidates':len(report['findings'])},
        'note':'File fan-out and source length are inventory metrics, not independent defect findings. Raw candidates and diagnostic occurrences remain in report.json.'}


def review_markdown(report):
    from .architecture import md_text
    review=report.get('review') or build_review(report);coverage=review['coverage'];counts=coverage['counts']
    lines=['## What was extracted','',f"{report['summary']['files']} source files · {report['summary']['classes']} classes · {report['summary']['relationships']} recorded relationships",'']
    for system in review['systems']:
        lines += ['- **'+md_text(system['name'])+'** · '+md_text(system['kind'])+f": {system['requests']} HTTP request sites; {system['unique_path_candidates']} unique local method/path candidates, {system['ambiguous']} ambiguous, {system['unlinked']} unlinked."]
    if review['systems']:lines+=['','Configured hosts, runtime middleware and request execution were not verified. Open a feature flow for the recorded handler, data and UI path.','']
    lines+=['## Review queue','',f"{len(review['items'])} grouped review items. Coverage gaps and closed dependency paths are presented separately from file-size / fan-out metrics.",'']
    for item in review['items'][:30]:
        lines+=['### '+md_text(item['priority']+' · '+item['title']),'',md_text(item['explanation']),'','Next step: '+md_text(item['next_step']),'']
        for e in item['evidence'][:12]:
            text=e.get('expression') or e.get('message','')
            lines+=['- `'+md_text(e['path'])+':'+str(e.get('line',1))+'` · '+md_text(text)]
        if len(item['evidence'])>12:lines+=['- Additional source anchors are retained in report.json.']
        lines+=['']
    lines+=['## Analysis coverage','',f"Parser exclusions: {counts.get('parser exclusions',0)} · skipped files: {counts.get('skipped files',0)} · unresolved local code imports: {counts.get('unresolved local imports',0)}.",
        '',f"Unresolved dynamic/external reference occurrences: {counts.get('dynamic / external references',0)}; global-shaped references: {counts.get('global-shaped references',0)}. These counts describe resolution limits and are not code-error counts.",'',
        f"Non-source resource imports: {counts.get('non-source resource imports',0)}. Raw diagnostics: {coverage['raw_occurrences']} occurrences, grouped into {len(coverage['groups'])} entries.",'',
        '## Inventory metrics','',f"{review['metrics']['large_definitions']} definitions meet the ≥80-line threshold; {review['metrics']['coupled_files']} files meet the ≥5-reference fan-out threshold. These measures alone do not justify a refactor.",'',review['note'],'']
    return '\n'.join(lines)
