"""Source-backed React/Axios/Express journeys. Never import project code.

Endpoint matches describe compatible path patterns, not proven runtime traffic.
Unresolved origins, handlers and service indirection stay explicit.
"""
import hashlib
import posixpath
import re
import textwrap
from html import escape
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from .core import checkpoint, decode_source
from .languages import language_for
from .syntax import grammar,source_tree

METHODS={'get','post','put','patch','delete','head','options'}
FUNCTIONS={'function_declaration','function_expression','arrow_function','method_definition'}
LIMITS=[
    'ES-module React/Axios/fetch and Express literal routes/mounts are supported statically. CommonJS wiring and other frameworks remain code structure only.',
    'Matching method and URL path is a candidate connection: configured hosts, proxies, runtime dispatch and authorization are not verified.',
    'Handler branches and data operations are source facts, not a simulation. Service wrappers, computed routes and indirect response transformations can remain unresolved.',
    'No repository code or API requests were executed. Unsupported or ambiguous links are not replaced with guessed connections.'
]


def walk(node):
    pending=[node]
    while pending:
        n=pending.pop();yield n;pending.extend(reversed(n.named_children))


def txt(n,raw):return raw[n.start_byte:n.end_byte].decode('utf-8') if n is not None else ''
def field(n,name):return n.child_by_field_name(name) if n is not None else None
def arguments(n):return list(field(n,'arguments').named_children) if field(n,'arguments') is not None else []


def literal(n,raw):
    if n is None or n.type not in {'string','template_string'}:return None
    parts=[]
    for c in n.named_children:
        if c.type=='template_substitution':parts.append('{'+txt(c,raw)[2:-1].strip()+'}')
        elif c.type in {'string_fragment','escape_sequence'}:parts.append(txt(c,raw))
    return ''.join(parts)


def member(n,raw):
    if n is None or n.type!='member_expression':return None,None
    return txt(field(n,'object'),raw),txt(field(n,'property'),raw)


def function_name(n,raw):
    name=field(n,'name')
    if name is not None:return txt(name,raw)
    if n.parent is not None and n.parent.type=='variable_declarator':return txt(field(n.parent,'name'),raw)
    return '<callback>'


def owners(n,raw):
    result=[];parent=n.parent
    while parent is not None:
        if parent.type in FUNCTIONS:
            name=function_name(parent,raw)
            if name!='<callback>':result.append((name,parent.start_point.row+1))
        parent=parent.parent
    return result


def block_key(n):
    while n is not None and n.type not in {'statement_block','program'}:n=n.parent
    return (n.start_byte,n.end_byte) if n is not None else None


def shadowed(n,name,raw):
    parent=n.parent
    while parent is not None:
        if parent.type in FUNCTIONS:
            parameters=field(parent,'parameters') or field(parent,'parameter')
            if parameters is not None and any(c.type=='identifier' and txt(c,raw)==name for c in walk(parameters)):return True
            body=field(parent,'body')
            if body is not None:
                for c in walk(body):
                    if c.type=='variable_declarator' and txt(field(c,'name'),raw)==name:return True
        parent=parent.parent
    return False


def resolve_import(path,spec,paths):
    if not spec.startswith('.'):return None
    base=posixpath.normpath(posixpath.join(posixpath.dirname(path),spec))
    choices=[base]+[base+ext for ext in ('.js','.jsx','.ts','.tsx','.mjs','.cjs')]+[base+'/index'+ext for ext in ('.js','.jsx','.ts','.tsx')]
    matches=list(dict.fromkeys(p for p in choices if p in paths))
    return matches[0] if len(matches)==1 else None


def keys(n,raw):
    if n is None:return []
    if n.type not in {'object','object_pattern'}:return []
    return [txt(field(c,'key'),raw) or txt(c,raw) for c in n.named_children if c.type in {'pair','pair_pattern','shorthand_property_identifier','shorthand_property_identifier_pattern'}]


def fact(path,n,**values):return {'path':path,'line':n.start_point.row+1,**values}


def public_url(value):
    """Keep useful endpoint/query structure without copying credential values."""
    names=r'key|api[_-]?key|access[_-]?token|token|auth|authorization|client[_-]?secret|secret|password|passwd|appid|jwt|signature|sig|subscription-key|x-api-key'
    value=re.sub(r'([?&](?:'+names+r')=)[^&#\s]+',lambda m:m.group(1)+'[redacted]',value,flags=re.I)
    return re.sub(r'(https?://)[^/@\s]+:[^/@\s]+@',r'\1[redacted]@',value)


def handler_facts(path,node,raw,imports):
    """Summaries deliberately expose field names, not credentials/literal values."""
    data=[];responses=[];inputs=[];conditions=[];objects={};helpers=[]
    children=[];pending=[node]
    while pending:
        current=pending.pop()
        if current!=node and current.type in FUNCTIONS:continue
        children.append(current);pending.extend(reversed(current.named_children))
    for n in children:
        if n.type=='variable_declarator':
            value=field(n,'value')
            if value is not None and value.type=='object':objects[txt(field(n,'name'),raw)]=value
            receiver,prop=member(value,raw)
            if receiver=='req' and prop in {'params','query','body'}:
                inputs+=['req.'+prop+'.'+key for key in keys(field(n,'name'),raw)]
        if n.type=='member_expression':
            expression=txt(n,raw)
            if re.fullmatch(r'req\.(params|query|body)\.[A-Za-z_$][\w$]*',expression):inputs.append(expression)
        if n.type=='if_statement':
            condition=field(n,'condition');value=txt(condition,raw)
            # Preserve operators and negation; do not publish arbitrary string
            # literals from a condition into the generated design summary.
            masks=[c for c in walk(condition) if c.type in {'string','template_string'}] if condition is not None else []
            for c in sorted(masks,key=lambda c:c.start_byte,reverse=True):
                start=len(raw[condition.start_byte:c.start_byte].decode('utf-8'));end=len(raw[condition.start_byte:c.end_byte].decode('utf-8'));value=value[:start]+"'<text>'"+value[end:]
            conditions.append(fact(path,n,description='Condition: '+value[:150]))
        if n.type!='call_expression':continue
        callee=field(n,'function');receiver,method=member(callee,raw);args=arguments(n)
        if callee is not None and callee.type=='identifier':
            name=txt(callee,raw)
            if name not in {'String','Number','Boolean','Error','parseInt','parseFloat'}:helpers.append(fact(path,n,name=name,definition=imports.get(name,{}).get('path')))
        binding=imports.get(receiver,{})
        if method in {'find','findOne','findById','create','save','updateOne','findOneAndUpdate','deleteOne','findByIdAndDelete','aggregate','countDocuments'} and binding.get('path'):
            data.append(fact(path,n,operation=receiver+'.'+method,model_path=binding['path'],filter_fields=keys(args[0],raw) if args else []))
        if method not in {'json','send'}:continue
        status=None;owner=field(callee,'object')
        if owner is not None and owner.type=='call_expression':
            status_receiver,status_method=member(field(owner,'function'),raw);status_args=arguments(owner)
            if status_receiver=='res' and status_method=='status' and status_args and status_args[0].type=='number':status=txt(status_args[0],raw)
            else:continue
        elif receiver!='res':continue
        value=args[0] if args else None
        if value is not None and value.type=='identifier':value=objects.get(txt(value,raw))
        responses.append(fact(path,n,status=status or 'default',fields=keys(value,raw),shape_known=value is not None and value.type=='object'))
    return {'inputs':sorted(set(inputs)),'conditions':conditions[:12],'data':data[:12],'responses':responses[:12],'helpers':helpers[:12]}


def scan_module(path,source,paths,cancel):
    from tree_sitter import Parser
    raw=source.encode('utf-8');root=source_tree(path,raw).root_node
    if root.has_error:return None
    nodes=list(walk(root));imports={};exports={};routers=set();router_kinds={};clients={};routes=[];mounts=[];requests=[];handlers={};states=[];renders=[]
    for n in nodes:
        if n.type=='import_statement':
            spec=literal(field(n,'source'),raw);clause=next((c for c in n.named_children if c.type=='import_clause'),None)
            if spec is None or clause is None:continue
            for c in clause.named_children:
                if c.type=='identifier':imports[txt(c,raw)]={'path':resolve_import(path,spec,paths),'name':'default','spec':spec}
                elif c.type=='named_imports':
                    for s in c.named_children:
                        name=txt(field(s,'name'),raw);alias=txt(field(s,'alias'),raw) or name
                        imports[alias]={'path':resolve_import(path,spec,paths),'name':name,'spec':spec}
        if n.type=='export_statement':
            value=field(n,'value');declaration=field(n,'declaration')
            if value is not None and value.type=='identifier':exports['default']=txt(value,raw)
            if declaration is not None:
                defs=[declaration] if declaration.type=='function_declaration' else [c for c in declaration.named_children if c.type=='variable_declarator']
                for d in defs:
                    name=txt(field(d,'name'),raw)
                    if name:exports['default' if any(c.type=='default' for c in n.children) else name]=name
    for n in nodes:
        checkpoint(cancel)
        if n.type=='variable_declarator':
            name=txt(field(n,'name'),raw);value=field(n,'value')
            if value is not None and value.type=='call_expression':
                fn=field(value,'function');owner,method=member(fn,raw);args=arguments(value)
                expr=txt(fn,raw)
                if imports.get(expr,{}).get('spec')=='express' and imports.get(expr,{}).get('name') in {'default','Router'} or method=='Router' and imports.get(owner,{}).get('spec')=='express':
                    routers.add(name);router_kinds[name]='application' if imports.get(expr,{}).get('name')=='default' else 'router'
                if method=='create' and imports.get(owner,{}).get('spec')=='axios':
                    config=args[0] if args else None;base=None
                    if config is not None and config.type=='object':
                        basepair=next((c for c in config.named_children if txt(field(c,'key'),raw)=='baseURL'),None)
                        base=literal(field(basepair,'value'),raw)
                    clients[name]={'base':base,'configured':True,'path':path,'line':n.start_point.row+1}
                if txt(fn,raw)=='useState' and field(n,'name').type=='array_pattern':
                    names=field(n,'name').named_children
                    if len(names)==2:states.append({'state':txt(names[0],raw),'setter':txt(names[1],raw),'owners':owners(n,raw)})
        if n.type in FUNCTIONS:
            name=function_name(n,raw)
            if name!='<callback>':handlers[(name,n.start_point.row+1)]={**fact(path,n,name=name),**handler_facts(path,n,raw,imports)}
        if n.type!='call_expression':continue
        fn=field(n,'function');receiver,method=member(fn,raw);args=arguments(n);url=literal(args[0],raw) if args else None
        if receiver in routers and method in METHODS|{'use'} and url is not None:
            rest=[txt(arg,raw) for arg in args[1:] if arg.type=='identifier']
            if method=='use' and rest:
                mounts.append(fact(path,n,receiver=receiver,prefix=url,targets=rest,middleware=[],
                    argument_labels=[txt(a,raw) if a.type=='identifier' else txt(field(a,'function'),raw)+'(…)' if a.type=='call_expression' else '<dynamic middleware>' for a in args[1:]]))
            elif method in METHODS:
                handler=rest[-1] if rest else None
                inline=next((a for a in args[1:] if a.type in FUNCTIONS),None)
                routes.append(fact(path,n,receiver=receiver,url=url,method=method.upper(),handler=handler,middleware=rest[:-1],inline=handler_facts(path,inline,raw,imports) if inline is not None else None))
        if url is not None and (method in METHODS or txt(fn,raw)=='fetch'):
            verb=method.upper() if method in METHODS else 'GET'
            if txt(fn,raw)=='fetch' and len(args)>1 and args[1].type=='object':
                pair=next((c for c in args[1].named_children if txt(field(c,'key'),raw)=='method'),None)
                verb=(literal(field(pair,'value'),raw) or 'GET').upper()
            # Binding is resolved later; a database .get() is never an HTTP client.
            binding=None;parent=n.parent
            while parent is not None and parent.type in {'await_expression','parenthesized_expression'}:parent=parent.parent
            if parent is not None and parent.type=='variable_declarator':binding=txt(field(parent,'name'),raw)
            requests.append(fact(path,n,receiver=receiver or 'fetch',method=verb,url=url,owners=owners(n,raw),binding=binding,fetch=txt(fn,raw)=='fetch'))
            requests[-1].update(shadowed=shadowed(n,receiver or 'fetch',raw),binding_scope=block_key(n),at=n.start_byte)
        if method=='map':renders.append(fact(path,n,state=receiver,owners=owners(n,raw)))
    for req in requests:
        req['updates']=[]
        for state in states:
            if not any(o in req['owners'] for o in state['owners']):continue
            for n in nodes:
                if n.type!='call_expression' or txt(field(n,'function'),raw)!=state['setter'] or owners(n,raw)!=req['owners'] or block_key(n)!=req['binding_scope'] or n.start_byte<=req['at']:continue
                args=arguments(n);value=txt(args[0],raw) if args else ''
                if req['binding'] and (value==req['binding'] or value.startswith(req['binding']+'.')):
                    req['updates'].append(fact(path,n,state=state['state'],setter=state['setter'],value=value,
                        renders=[r for r in renders if r['state']==state['state'] and any(o in r['owners'] for o in state['owners'])]))
    return {'path':path,'imports':imports,'exports':exports,'routers':routers,'router_kinds':router_kinds,'clients':clients,'routes':routes,'mounts':mounts,'requests':requests,'handlers':handlers}


def analyze_flows(snapshot,cancel=None,progress=lambda value:None):
    paths=set(snapshot.hashes);modules={};warnings=[];total=0
    root=Path(snapshot.root).resolve()
    for path,digest in sorted(snapshot.hashes.items()):
        checkpoint(cancel)
        if language_for(path) not in {'javascript','typescript','tsx'} or digest in {'oversized','unreadable'}:continue
        if re.search(r'(firebase-adminsdk|service.?account|credential|secret)',path,re.I):continue
        target=root/path
        if target.is_symlink() or not target.resolve().is_relative_to(root):raise ValueError('Project paths changed during flow review.')
        raw=target.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Project changed during flow review. Review again.')
        if len(raw)>512_000 or total+len(raw)>32_000_000:
            warnings.append('Flow parser size limit: '+path);continue
        total+=len(raw)
        module=scan_module(path,decode_source(raw,path),paths,cancel)
        if module:modules[path]=module
        else:warnings.append('Flow parser skipped syntax errors: '+path)
    progress('Matching client requests to mounted server routes…')

    def binding(path,name,seen=None):
        seen=set() if seen is None else seen
        if (path,name) in seen:return None
        seen.add((path,name));mod=modules.get(path)
        if not mod:return None
        imp=mod['imports'].get(name)
        if imp and imp['path'] in modules:
            target=modules[imp['path']]['exports'].get(imp['name'])
            if target:return binding(imp['path'],target,seen)
            return None
        return path,name

    parents=defaultdict(list);route_rows=[]
    for path,mod in modules.items():
        for mount in mod['mounts']:
            choices=[]
            for name in mount['targets']:
                target=binding(path,name)
                if target and target[1] in modules.get(target[0],{}).get('routers',set()):choices.append((name,target))
            owner=binding(path,mount['receiver'])
            if len(choices)==1 and owner:
                name,target=choices[0]
                evidence={k:v for k,v in mount.items() if k not in {'targets','argument_labels'}}
                evidence.update(target=name,middleware=[label for label in mount['argument_labels'] if label!=name])
                parents[target].append((owner,evidence))

    def prefixes(key,seen=None):
        seen=set() if seen is None else seen
        if key is None or key in seen:return []
        if not parents.get(key):return [('',[],modules.get(key[0],{}).get('router_kinds',{}).get(key[1])=='application')]
        result=[]
        for parent,mount in parents[key]:
            for prefix,evidence,known in prefixes(parent,seen|{key}):
                result.append((prefix.rstrip('/')+'/'+mount['prefix'].lstrip('/'),evidence+[mount],known))
        return result[:24]

    for path,mod in modules.items():
        for route in mod['routes']:
            key=binding(path,route['receiver']);handler=None
            if route['handler']:
                handlerkey=binding(path,route['handler'])
                if handlerkey:
                    matches=[h for (name,line),h in modules.get(handlerkey[0],{}).get('handlers',{}).items() if name==handlerkey[1]]
                    if len(matches)==1:handler=matches[0]
            if route['inline'] is not None:handler={**route['inline'],'path':path,'line':route['line'],'name':'inline handler'}
            for prefix,mounts,complete in prefixes(key):
                endpoint=prefix.rstrip('/')+'/'+route['url'].lstrip('/')
                route_rows.append({**route,'endpoint':endpoint,'mounts':mounts,'mount_complete':complete,'handler_detail':handler})
    flows=[];unresolved_clients=0
    from .polyglot import INFERRED_KINDS
    reverse=defaultdict(list)
    for e in snapshot.edges:
        if e['kind'] not in INFERRED_KINDS:reverse[e['callee']].append(e)
    owner_symbols={(s.path,s.start,s.name):s for s in snapshot.symbols.values()}
    for path,mod in modules.items():
        for req in mod['requests']:
            checkpoint(cancel);client=binding(path,req['receiver']);config=None
            if req['shadowed']:continue
            if client:config=modules.get(client[0],{}).get('clients',{}).get(client[1])
            direct=mod['imports'].get(req['receiver'],{}).get('spec')=='axios'
            if not req['fetch'] and config is None and not direct:continue
            if req['fetch'] and ('fetch' in mod['imports'] or any(name=='fetch' for name,line in mod['handlers'])):
                unresolved_clients+=1;continue
            url=req['url'];base=config['base'] if config else ''
            if base and not re.match(r'https?://',url):url=base.rstrip('/')+'/'+url.lstrip('/')
            if url.startswith(('https://','http://')):endpoint=urlsplit(url).path
            elif url.startswith('/'):endpoint=url.split('?',1)[0].split('#',1)[0]
            else:endpoint=None
            matches=[r for r in route_rows if endpoint is not None and r['mount_complete'] and r['method']==req['method'] and compatible(endpoint,r['endpoint'])]
            name=req['owners'][-1][0] if req['owners'] else Path(path).stem
            visible_url=public_url(req['url'])
            flow={**req,'url':visible_url,'id':hashlib.sha256(f'{path}:{req["line"]}:{req["method"]}:{req["url"]}'.encode()).hexdigest()[:16],
                'title':name+' · '+req['method']+' '+visible_url,'app':consumer_role(path,snapshot.profile)[0],'consumer_kind':consumer_role(path,snapshot.profile)[1],'endpoint':endpoint,
                'origin':'Configured client origin is not verified' if config else 'Request origin is not verified',
                'matches':matches,'status':'path match' if len(matches)==1 else 'ambiguous' if matches else 'unresolved',
                'notes':[]}
            owner=req['owners'][0] if req['owners'] else None
            symbol=owner_symbols.get((path,owner[1],owner[0])) if owner else None
            flow['callers']=[]
            if symbol:
                for e in reverse.get(symbol.id,[])[:12]:
                    caller=snapshot.symbols.get(e['caller'])
                    if caller and not caller.is_test and caller.kind!='module':flow['callers'].append({**e,'path':caller.path,'name':caller.qualname,'definition_line':caller.start})
            if not matches:flow['notes'].append('No unique local server route was linked. The service may be external, computed, unsupported, or outside this project.')
            if len(matches)>1:flow['notes'].append('Multiple server routes match this method and path; none was selected as the runtime destination.')
            if endpoint is None:flow['notes'].append('The URL path depends on a dynamic prefix; no endpoint match was guessed.')
            flows.append(flow)
    return {'version':1,'flows':flows,'routes':route_rows,'limits':LIMITS,'warnings':warnings,
            'summary':{'requests':len(flows),'path_matches':sum(f['status']=='path match' for f in flows),
                'unresolved':sum(f['status']=='unresolved' for f in flows),'ambiguous':sum(f['status']=='ambiguous' for f in flows),'server_routes':len(route_rows),
                'analyzed_modules':len(modules),'skipped_files':len(warnings)}}


def compatible(client,server):
    def pieces(value):return value.rstrip('/').split('/')
    a,b=pieces(client),pieces(server)
    return len(a)==len(b) and all(x==y or (y.startswith(':') and bool(x)) or (x.startswith('{') and x.endswith('}') and bool(y)) for x,y in zip(a,b))


def app_name(path):
    parts=path.split('/')
    return '/'.join(parts[:parts.index('src')]) or 'Project UI' if 'src' in parts else parts[0] if len(parts)>1 else 'Project'


def consumer_role(path,profile):
    packages=[]
    for manifest,data in profile.get('manifests',{}).items():
        if not manifest.endswith('package.json') or not isinstance(data,dict):continue
        directory=posixpath.dirname(manifest)
        if directory and not path.startswith(directory+'/'):continue
        packages.append((directory,data))
    if packages:
        directory,data=max(packages,key=lambda row:len(row[0]));dependencies=set(data.get('dependencies',{}))|set(data.get('devDependencies',{}))
        if dependencies&{'react','next','vue','@angular/core','svelte'}:return directory or 'Web application','Web application (manifest)'
        if dependencies&{'express','fastify','@nestjs/core','koa'}:return (directory+' / ' if directory else '')+'Server outbound requests','Server HTTP consumer (manifest)'
    return app_name(path),'HTTP consumer (role unverified)'


def design_model(report,flow=None):
    """Editable HLD systems or a branching request/response implementation view."""
    nodes=[];edges=[];analysis=report.get('feature_flows',{})
    def node(key,title,kind,path='',line=1,facts=(),column=0,row=0):
        nodes.append({'id':key,'title':title,'kind':kind,'path':path,'line':line,'fields':[],
            'operations':list(facts),'x':column*460,'y':row*360,'origin':'extracted'});return key
    def edge(a,b,label,kind='source association'):
        edges.append({'id':str(len(edges)),'from':a,'to':b,'label':label,'classification':kind,'origin':'extracted'})
    if flow is None:
        grouped=defaultdict(list)
        for f in analysis.get('flows',[]):grouped[f['app']].append(f)
        for i,(app,rows) in enumerate(sorted(grouped.items())[:20]):
            a=node('app:'+app,app,rows[0].get('consumer_kind','HTTP consumer'),rows[0]['path'],rows[0]['line'],
                [str(len(rows))+' source requests',str(sum(bool(f['matches']) for f in rows))+' with compatible local route paths'],0,i)
            servers=defaultdict(list)
            for f in rows:
                for match in f['matches']:servers[match['mounts'][0]['path'] if match['mounts'] else match['path']].append(match)
            for j,(server,matches) in enumerate(sorted(servers.items())[:3]):
                key='server:'+app+':'+server
                node(key,Path(server).name,'Server route entry',server,1,[str(len(matches))+' compatible request paths','Configured origin / proxy not verified'],1,i+j)
                edge(a,key,'HTTP candidates','path match')
                models=sorted({d['model_path'] for m in matches for d in (m['handler_detail'] or {}).get('data',[])})
                if models:
                    data_key='data:'+key;node(data_key,'Data models','Imported model operations',models[0],1,[Path(p).stem for p in models][:8],2,i+j)
                    edge(key,data_key,'model operations','source association')
        if not nodes:node('unknown','No supported request flow extracted','Coverage gap',facts=['Code structure is available separately.','No system flow was invented for this framework.'])
    else:
        request=node('request',flow['owners'][-1][0] if flow['owners'] else 'Client request','Client request',flow['path'],flow['line'],
            [flow['method']+' '+flow['url'],flow['origin']],0,0)
        for i,caller in enumerate(flow.get('callers',[])[:3]):
            key='caller'+str(i);node(key,caller['name'],'Source caller',caller['path'],caller['line'],['References the request wrapper at this line.','Runtime ordering / data propagation not established.'],0,i+3)
            edge(key,request,'calls wrapper','resolved static')
        for i,match in enumerate(flow['matches'][:4]):
            r=node('route'+str(i),match['method']+' '+match['endpoint'],'Route candidate',match['path'],match['line'],
                ['Mount '+m['prefix']+' · '+(', '.join(m['middleware']) or 'no named middleware') for m in match['mounts']]+['Route middleware: '+(', '.join(match['middleware']) or 'none recorded')],1,i*2)
            edge(request,r,'path match','path match')
            h=match['handler_detail'];key='handler'+str(i)
            if h:
                info=['Input: '+', '.join(h['inputs'])] if h['inputs'] else ['Input field extraction unresolved']
                info += [d['operation']+' · filter fields: '+(', '.join(d['filter_fields']) or 'not statically known') for d in h['data']]
                info += [c['description'] for c in h['conditions'][:5]]
                info += ['Helper call: '+v['name']+'(…)' for v in h.get('helpers',[])[:4]]
                node(key,h['name'],'Handler logic',h['path'],h['line'],info,2,i*2);edge(r,key,'handler','resolved static')
                for k,data in enumerate(h['data'][:3]):
                    data_key=key+':data'+str(k)
                    node(data_key,Path(data['model_path']).stem,'Data operation',data['model_path'],1,
                        [data['operation'],'Filter fields: '+(', '.join(data['filter_fields']) or 'not statically known'),'Call site: '+Path(data['path']).name+':'+str(data['line'])],2,i*2+k+1)
                    edge(key,data_key,'data operation','resolved static')
                for k,response in enumerate(h['responses'][:4]):
                    responsekey=key+':response'+str(k)
                    node(responsekey,'HTTP '+response['status'],'Alternative response branch',response['path'],response['line'],
                        ['JSON fields: '+(', '.join(response['fields']) if response['shape_known'] else 'shape unresolved'),'Branch selection is runtime-dependent'],3,i*2+k)
                    edge(key,responsekey,'response branch','source association')
            else:
                node(key,'Handler unresolved','Coverage gap',match['path'],match['line'],['Dynamic or unsupported handler binding.'],2,i*2);edge(r,key,'Unresolved registration','inferred')
        if not flow['matches']:
            node('unresolved','Server connection unresolved','Coverage gap',facts=flow['notes'],column=1);edge(request,'unresolved','No local endpoint match','inferred')
        for i,update in enumerate(flow['updates'][:4]):
            key='state'+str(i);node(key,update['setter'],'Client response → state',update['path'],update['line'],[update['value']+' → '+update['state']],0,i+1)
            edge(request,key,'result → state','static response use')
            for match_index,match in enumerate(flow['matches'][:4]):
                for response_index,response in enumerate((match['handler_detail'] or {}).get('responses',[])[:4]):
                    if response['status'].startswith('2'):
                        edge('handler'+str(match_index)+':response'+str(response_index),key,'response candidate','path match')
            for j,render in enumerate(update['renders'][:3]):
                rendered=key+':render'+str(j);node(rendered,update['state']+'.map(…)','UI rendering',render['path'],render['line'],['State is referenced in list rendering.'],1,i+j+2)
                edge(key,rendered,'renders state','static state use')
        if not flow['updates']:
            node('ui-unknown','UI response handling unresolved','Coverage gap',flow['path'],flow['line'],['No direct request-result → state setter was resolved.','A service wrapper or another state mechanism may be involved.'],0,1)
            edge(request,'ui-unknown','Not inferred from proximity','inferred')
    heights={}
    for n in sorted(nodes,key=lambda n:(n['x'],n['y'])):
        n['y']=max(n['y'],heights.get(n['x'],0));heights[n['x']]=n['y']+card_height(n)+65
    return {'format':'changelens-design','version':1,'snapshot_id':report['snapshot_id'],'project':report['project'],
        'level':'LLD' if flow else 'HLD','scope':flow['id'] if flow else 'systems','page':0,'nodes':nodes,'edges':edges,
        'notice':'Source-backed flow draft · endpoint paths are candidates, not proven runtime connections. Edits change this diagram only.'}


def card_height(n):return max(125,100+18*sum(max(1,len(textwrap.wrap(v,44))) for v in n['operations']))


def model_svg(model):
    """Standalone source-analysis diagram. User drafts export through the canvas."""
    nodes=model['nodes'];by_id={n['id']:n for n in nodes}
    width=max((n['x']+410 for n in nodes),default=500);height=max((n['y']+card_height(n)+110 for n in nodes),default=200)
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="-20 -65 {width} {height}">',
        '<rect x="-20" y="-65" width="100%" height="100%" fill="#171d25"/>',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#8daea9"/></marker></defs>',
        '<g font-family="Segoe UI, sans-serif" fill="#dce5df"><text y="-35">'+model['level']+' · source flow · snapshot '+escape(model['snapshot_id'])+'</text>']
    for e in model['edges']:
        a,b=by_id[e['from']],by_id[e['to']];x,y=a['x']+365,a['y']+45;u,v=b['x'],b['y']+45
        if a['x']==b['x']:x=a['x']+365;u=b['x']+365;bend=x+55
        else:bend=(x+u)/2
        dash='' if e['classification']=='resolved static' else ' stroke-dasharray="5 4"'
        svg.append(f'<path d="M{x},{y} C{bend},{y} {bend},{v} {u},{v}" fill="none" stroke="#8daea9"{dash} marker-end="url(#arrow)"/>')
        svg.append(f'<text x="{min(x,u)+5}" y="{(y+v)/2-8}" font-size="10">{escape(e["label"])}</text>')
    for n in nodes:
        x,y=n['x'],n['y'];h=card_height(n)
        svg.append(f'<g><rect x="{x}" y="{y}" width="365" height="{h}" rx="7" fill="#232e39" stroke="#435967"/><text x="{x+14}" y="{y+24}" font-size="14">{escape(n["title"][:46])}</text><text x="{x+14}" y="{y+46}" font-size="11" fill="#92bfae">{escape(n["kind"])}</text>')
        rows=[n.get('path','')+(':'+str(n['line']) if n.get('path') else '')]+n['operations'];offset=70
        for row in rows:
            for line in textwrap.wrap(row,49) or ['']:
                svg.append(f'<text x="{x+14}" y="{y+offset}" font-size="11">{escape(line)}</text>');offset+=18
        svg.append('</g>')
    return '\n'.join(svg+['</g></svg>'])


def flows_markdown(report):
    analysis=report.get('feature_flows',{});lines=['# System and feature flows','',
        'Snapshot: `'+report['snapshot_id']+'`','',
        '![System overview](systems.svg)','',
        'Method/path matches are candidates; host configuration and runtime dispatch have not been verified.','']
    for flow in analysis.get('flows',[]):
        lines+=['## '+flow['title'].replace('<','&lt;'),'',flow['path']+':'+str(flow['line'])+' · '+flow['status'],'',
            '[Implementation flow](flows/'+flow['id']+'.svg)','']
        for match in flow['matches']:
            lines+=['- Route candidate: '+match['method']+' '+match['endpoint']+' at '+match['path']+':'+str(match['line'])]
            for mount in match['mounts']:lines+=['- Mount: '+mount['prefix']+' at '+mount['path']+':'+str(mount['line'])+'; middleware '+', '.join(mount['middleware'])]
            h=match['handler_detail']
            if h:
                lines+=['- Handler: '+h['name']+' at '+h['path']+':'+str(h['line']),'- Input fields: '+', '.join(h['inputs'])]
                for data in h['data']:lines+=['- Data operation: '+data['operation']+'; filter fields '+', '.join(data['filter_fields'])+' at '+data['path']+':'+str(data['line'])]
                for response in h['responses']:lines+=['- Alternative response: HTTP '+response['status']+'; fields '+', '.join(response['fields'])+' at '+response['path']+':'+str(response['line'])]
            else:lines+=['- Handler unresolved.']
        for update in flow['updates']:
            lines+=['- Client update: '+update['value']+' → '+update['setter']+' at '+update['path']+':'+str(update['line'])]
            for render in update['renders']:lines+=['- Rendering: '+render['state']+'.map at '+render['path']+':'+str(render['line'])]
        lines+=['- '+note for note in flow['notes']]+['']
    lines+=['## Coverage limits','']+['- '+line for line in analysis.get('limits',LIMITS)]
    return '\n'.join(lines)+'\n'
