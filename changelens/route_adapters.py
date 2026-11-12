"""Explicit Next App Router and single-module Python HTTP registrations.

Extract source facts only. These adapters never load framework/project modules.
"""
import ast
import hashlib
import re
from pathlib import Path,PurePosixPath
from .core import checkpoint,decode_source

VERBS={'GET','POST','PUT','PATCH','DELETE','OPTIONS','HEAD'}


def framework_routes(snapshot,modules,binding,cancel=None):
    routes=[];warnings=[]
    next_roots=[]
    for path,data in snapshot.profile.get('manifests',{}).items():
        deps={**data.get('dependencies',{}),**data.get('devDependencies',{})}
        if path.endswith('package.json') and 'next' in deps:next_roots.append(str(PurePosixPath(path).parent))
    for path,mod in modules.items():
        checkpoint(cancel)
        parts=PurePosixPath(path).parts
        if PurePosixPath(path).stem!='route' or 'app' not in parts:continue
        roots=[r for r in next_roots if r=='.' or path.startswith(r+'/')]
        if not roots:continue
        root=max(roots,key=len);relative=PurePosixPath(path).relative_to(root) if root!='.' else PurePosixPath(path)
        segment=list(relative.parts)
        if segment[:2]==['src','app']:segment=segment[2:-1]
        elif segment[:1]==['app']:segment=segment[1:-1]
        else:continue
        if any('...' in p or p.startswith('@') for p in segment):warnings.append('Next route pattern not expanded: '+path);continue
        segment=[p for p in segment if not (p.startswith('(') and p.endswith(')'))]
        endpoint='/'+'/'.join(':'+p[1:-1] if p.startswith('[') and p.endswith(']') else p for p in segment)
        for verb,name in mod['exports'].items():
            if verb not in VERBS:continue
            target=binding(path,name)
            choices=[h for (n,_),h in modules.get(target[0] if target else '',{}).get('handlers',{}).items() if target and n==target[1]]
            handler=choices[0] if len(choices)==1 else None
            routes.append({'path':path,'line':handler['line'] if handler and handler['path']==path else 1,'method':verb,'url':endpoint,'endpoint':endpoint,
                'mounts':[],'mount_complete':True,'middleware':[],'handler':name,'inline':None,'handler_detail':handler,'framework':'Next.js App Router'})
    for path,digest in snapshot.hashes.items():
        checkpoint(cancel)
        if not path.endswith('.py') or digest in {'oversized','unreadable'}:continue
        target=Path(snapshot.root)/path
        if target.is_symlink() or not target.resolve().is_relative_to(Path(snapshot.root).resolve()):raise ValueError('Project paths changed during route analysis.')
        raw=target.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Project changed during route analysis.')
        try:tree=ast.parse(decode_source(raw,path))
        except (SyntaxError,UnicodeError):continue
        imports={}
        for n in tree.body:
            if isinstance(n,ast.ImportFrom):
                for alias in n.names:imports[alias.asname or alias.name]=(n.module or '')+'.'+alias.name
        applications={}
        def constant(n):return n.value if isinstance(n,ast.Constant) and isinstance(n.value,str) else None
        for n in tree.body:
            if isinstance(n,ast.Assign) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name):
                constructor=imports.get(n.value.func.id,'')
                if constructor in {'fastapi.FastAPI','flask.Flask'}:
                    for name in n.targets:
                        if isinstance(name,ast.Name):applications[name.id]=constructor.split('.')[0]
        for n in tree.body:
            if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
            for decorator in n.decorator_list:
                if not isinstance(decorator,ast.Call) or not isinstance(decorator.func,ast.Attribute):continue
                owner=decorator.func.value
                if not isinstance(owner,ast.Name) or owner.id not in applications:continue
                verb=decorator.func.attr.upper();url=constant(decorator.args[0]) if decorator.args else None
                if not url:continue
                methods=[verb] if verb in VERBS else ['GET'] if verb=='ROUTE' else []
                for keyword in decorator.keywords:
                    if keyword.arg=='methods' and isinstance(keyword.value,(ast.List,ast.Tuple)):
                        methods=[constant(v).upper() for v in keyword.value.elts if constant(v) and constant(v).upper() in VERBS]
                endpoint=re.sub(r'\{([^}:]+)(?::[^}]+)?\}',r':\1',url)
                endpoint=re.sub(r'<(?:[^:>]+:)?([^>]+)>',r':\1',endpoint)
                default_status='200'
                for keyword in decorator.keywords:
                    if keyword.arg=='status_code':default_status=str(keyword.value.value) if isinstance(keyword.value,ast.Constant) and isinstance(keyword.value.value,int) else 'dynamic'
                responses=[];conditions=[];helpers=[];pending=[n]
                while pending:
                    child=pending.pop()
                    if child is not n and isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef,ast.Lambda,ast.ClassDef)):continue
                    pending.extend(reversed(list(ast.iter_child_nodes(child))))
                    if isinstance(child,ast.Return):
                        value=child.value;status=default_status
                        if isinstance(value,ast.Tuple) and len(value.elts)>=2:
                            status=str(value.elts[1].value) if isinstance(value.elts[1],ast.Constant) else 'dynamic';value=value.elts[0]
                        if isinstance(value,ast.Call) and isinstance(value.func,ast.Name) and imports.get(value.func.id)=='flask.jsonify':
                            fields=[k.arg for k in value.keywords if k.arg];known=True
                        else:fields=[k.value for k in value.keys if isinstance(k,ast.Constant) and isinstance(k.value,str)] if isinstance(value,ast.Dict) else [];known=isinstance(value,ast.Dict)
                        if isinstance(value,ast.Call):
                            for keyword in value.keywords:
                                if keyword.arg=='status_code':status=str(keyword.value.value) if isinstance(keyword.value,ast.Constant) and isinstance(keyword.value.value,int) else 'dynamic'
                        responses.append({'path':path,'line':child.lineno,'status':status,'fields':fields,'shape_known':known})
                    if isinstance(child,ast.Call) and isinstance(child.func,ast.Name):helpers.append({'path':path,'line':child.lineno,'name':child.func.id,'definition':None})
                    if isinstance(child,ast.If):conditions.append({'path':path,'line':child.lineno,'description':'Conditional branch; see source'})
                handler={'path':path,'line':n.lineno,'name':n.name,'inputs':[a.arg for a in n.args.args],'data':[],'responses':responses,'conditions':conditions,'helpers':helpers}
                for method in methods:routes.append({'path':path,'line':decorator.lineno,'method':method,'url':url,'endpoint':endpoint,'mounts':[],'mount_complete':True,'middleware':[],
                    'handler':n.name,'inline':None,'handler_detail':handler,'framework':applications[owner.id]})
    return routes,warnings
