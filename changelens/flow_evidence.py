"""Bounded, source-only joins for feature journeys. No project execution."""
import hashlib
import re
from collections import defaultdict
from copy import deepcopy
from .core import checkpoint


def identity(*parts):
    return hashlib.sha256(':'.join(map(str,parts)).encode()).hexdigest()[:20]


def enrich_flows(flows,modules,binding,snapshot,cancel=None):
    callers=defaultdict(list)
    for path,mod in modules.items():
        for call in mod.get('calls',[]):
            if not call['shadowed']:
                target=binding(path,call['name'])
                if target:callers[target].append(call)

    def helpers(handler,seen=(),depth=0):
        key=(handler['path'],handler['name'])
        if key in seen:return [],['Service helper cycle; expansion stopped']
        if depth>=6:return [],['Service depth limit reached']
        result=[];gaps=[]
        for call in handler.get('helpers',[]):
            checkpoint(cancel)
            if call.get('shadowed'):
                gaps.append('Helper '+call['name']+': locally shadowed binding');continue
            if len(result)>=48:gaps.append('Service expansion limit reached');break
            target=binding(call['path'],call['name'])
            choices=[h for (name,_),h in modules.get((target or ('',))[0],{}).get('handlers',{}).items() if target and name==target[1]]
            if len(choices)!=1:
                gaps.append('Helper '+call['name']+': local binding unresolved or ambiguous');continue
            child=deepcopy(choices[0]);child['call_site']={'path':call['path'],'line':call['line']};child['caller_name']=handler['name']
            nested,missing=helpers(child,seen+(key,),depth+1)
            result.append(child);result.extend(nested);gaps.extend(missing)
        return result,gaps

    for flow in flows:
        checkpoint(cancel)
        flow['snapshot_id']=snapshot.id;flow['gaps']=[];flow['service_chain']=[]
        flow['screen']=flow['owners'][-1][0] if flow['owners'] else flow['app'];flow['screens']=[]
        owner=flow['owners'][0] if flow['owners'] else None
        if owner:
            queue=[((flow['path'],owner[0]),flow,(),0)];expanded=set()
            while queue:
                target,request,seen,depth=queue.pop(0)
                if target in seen or depth>=6:
                    flow['gaps'].append('Request wrapper cycle or depth limit; propagation stopped');continue
                if target in expanded:continue
                expanded.add(target)
                wrappers=[w for (name,_),w in modules.get(target[0],{}).get('wrappers',{}).items() if name==target[1]]
                # Only a single direct return preserves a known result. No promise
                # transforms, branching returns or arbitrary expression guessing.
                returns=wrappers[0]['returns'] if len(wrappers)==1 else []
                value=returns[0].removeprefix('await ').strip() if len(returns)==1 else ''
                result=request.get('binding')
                direct=bool(result and re.fullmatch(re.escape(result)+r'(?:\.[A-Za-z_$][\w$]*)*',value))
                if not direct:
                    # Return-call forms are accepted only for this exact source call.
                    call_name=request.get('name') or (request['receiver']+'.'+request['method'].lower() if not request.get('fetch') else 'fetch')
                    direct=bool(request['at'] in (wrappers[0].get('return_calls',[]) if wrappers else []) and re.fullmatch(re.escape(call_name)+r'\([^()]*\)(?:\.[A-Za-z_$][\w$]*)*',value))
                if not direct:
                    if any(c['binding'] for c in callers.get(target,[])):flow['gaps'].append('Wrapper '+target[1]+': return transformation or branching is unsupported')
                    continue
                for call in callers.get(target,[]):
                    if len(flow['service_chain'])>=48:
                        flow['gaps'].append('Client wrapper expansion limit reached');break
                    site={'path':call['path'],'line':call['line'],'name':call['name'],'classification':'resolved service call'}
                    if site not in flow['service_chain']:flow['service_chain'].append(site)
                    for update in call['updates']:
                        if update not in flow['updates']:flow['updates'].append(deepcopy(update))
                        if call['owners'] and call['owners'][-1][0] not in flow['screens']:flow['screens'].append(call['owners'][-1][0])
                    if call['owners']:queue.append(((call['path'],call['owners'][0][0]),call,seen+(target,),depth+1))

        for route in flow['matches']:
            handler=route.get('handler_detail')
            if handler:
                route['service_helpers'],missing=helpers(handler)
                flow['gaps'].extend(missing)
            else:route['service_helpers']=[]
        if flow['screens']:flow['screen']=', '.join(flow['screens'])
        else:flow['screens']=[flow['screen']]
        flow['gaps']=list(dict.fromkeys(flow['gaps']+flow['notes']))
        steps=[];relations=[];step_keys={};step_counts=defaultdict(int)
        def step(kind,record,label):
            source_key=(kind,record.get('path'),record.get('line'),label)
            if source_key in step_keys:return step_keys[source_key]
            semantic=(kind,record.get('path'),label);step_counts[semantic]+=1
            key=identity(flow['id'],*semantic,step_counts[semantic]);step_keys[source_key]=key
            steps.append({'id':key,'kind':kind,'label':label,'source':{'path':record.get('path'),'line':record.get('line')},'snapshot_id':snapshot.id})
            return key
        def link(a,b,kind,record,description,classification='resolved static'):
            relations.append({'id':identity(a,b,kind),'from':a,'to':b,'kind':kind,'classification':classification,
                'evidence':[{'path':record.get('path'),'line':record.get('line'),'description':description}]})
        request=step('route entry' if flow.get('entry_kind')=='server' else 'request',flow,flow['method']+' '+flow['url'])
        for call in flow['service_chain']:
            key=step('service call',call,call['name']);link(key,request,'call',call,'Explicit request-wrapper binding')
        for route in flow['matches']:
            key=step('route',route,route['method']+' '+route['endpoint'])
            if flow.get('entry_kind')=='server':link(request,key,'route registration',route,'Explicit source registration; no client connection asserted')
            else:link(request,key,'HTTP candidate',flow,'Compatible method and mounted path; origin unverified','path match')
            parent=key
            for mount in route['mounts']:
                key=step('mount',mount,mount['prefix']);link(parent,key,'route registration',mount,'Explicit router mount; registration order preserved');parent=key
            handler=route.get('handler_detail')
            if not handler:continue
            key=step('handler',handler,handler['name']);link(parent,key,'call',route,'Registered route handler');parent=key
            for child in [handler]+route['service_helpers']:
                childkey=step('handler',child,child['name'])
                if child is not handler:
                    caller=next((s['id'] for s in steps if s['kind']=='handler' and s['source']['path']==child['call_site']['path'] and s['label']==child['caller_name']),parent)
                    link(caller,childkey,'call',child['call_site'],'Explicit service helper binding')
                for data in child['data']:
                    key=step('data operation',data,data['operation']);link(childkey,key,'data access',data,'Imported model operation; execution unverified')
                for response in child['responses']:
                    key=step('response',response,'HTTP '+response['status']);link(childkey,key,'response branch',response,'Possible response statement; branch execution unverified')
        for update in flow['updates']:
            key=step('state update',update,update['setter']);link(request,key,'state update',update,'Direct result member access passed to state setter')
            for render in update['renders']:
                rendered=step('render',render,render['state']);link(key,rendered,'render',render,'State referenced by list rendering')
        flow['steps']=steps;flow['relationships']=relations


def affected_features(analysis,changes,locations):
    """Join changed source ranges to feature witnesses, not filename similarity."""
    rows=[]
    changed=[locations[s] for s in changes.get('seeds',[]) if s in locations]
    for flow in analysis.get('flows',[])+analysis.get('server_flows',[]):
        evidence=[s for s in flow.get('steps',[]) if any(c['path']==s['source']['path'] and c.get('start',1)<=s['source'].get('line',0)<=c.get('end',10**9) for c in changed)]
        if evidence:rows.append({'id':flow['id'],'title':flow['title'],'app':flow['app'],'screen':flow['screen'],'evidence':evidence,'classification':'potential feature impact'})
    return rows
