"""Deterministic, evidence-backed architecture and implementation-level design.

Consumes indexed declarations only. Never imports or executes project code.
"""
import ast
from collections import defaultdict
from datetime import datetime, timezone
from html import escape
import json
import hashlib
from pathlib import Path
import tempfile
from .core import checkpoint, fingerprint, revision, module_name, decode_source
from .languages import language_for
from .polyglot import INFERRED_KINDS


LIMITS = [
    'Static implementation inventory, not a complete runtime architecture or proposed redesign.',
    'Dynamic calls, reflection, dependency injection, framework routing and external services may be unresolved.',
    'Relationships use language-adapter references plus exact local Python imports; conditional imports are potential dependencies. Absence of a link does not prove independence.',
    'Python and Dart member details are syntax-derived; other languages may have declaration excerpts only. Type resolution and runtime ownership are not proven.',
    'Complexity findings use disclosed size/fan-out thresholds, not measured defects or behavior guarantees.',
    'No repository modules, tests, model-generated code or external diagram renderer were executed.',
]


def components(adjacency, cancel=None):
    """Iterative Kosaraju SCCs, safe for large repository dependency chains."""
    seen=set();order=[]
    for start in sorted(adjacency):
        checkpoint(cancel)
        if start in seen:continue
        stack=[(start,False)]
        while stack:
            checkpoint(cancel);node,finish=stack.pop()
            if finish:order.append(node);continue
            if node in seen:continue
            seen.add(node);stack.append((node,True))
            stack.extend((target,False) for target in sorted(adjacency.get(node,()),reverse=True) if target not in seen)
    reverse={n:set() for n in adjacency}
    for node,targets in adjacency.items():
        for target in targets:reverse.setdefault(target,set()).add(node)
    seen=set();result=[]
    for start in reversed(order):
        if start in seen:continue
        group=[];stack=[start];seen.add(start)
        while stack:
            checkpoint(cancel);node=stack.pop();group.append(node)
            for target in reverse.get(node,()):
                if target not in seen:seen.add(target);stack.append(target)
        if len(group)>1:result.append(sorted(group))
    return sorted(result)


def declaration(symbol):
    """Exact location plus bounded declaration and Python AST detail."""
    row={'id':symbol.id,'path':symbol.path,'name':symbol.name,'qualname':symbol.qualname,
         'kind':symbol.kind,'start':symbol.start,'end':symbol.end,'is_test':symbol.is_test,
         'header':' '.join(symbol.source.strip().splitlines()[:3])[:350],
         'signature':None,'bases':[],'fields':[]}
    row['constructors']=[]
    if language_for(symbol.path)=='dart':
        from .declaration_details import dart_details
        row.update(dart_details(symbol))
    if language_for(symbol.path)=='python' and symbol.kind in {'class','function','async_function'}:
        from .python_source import symbol_node
        try:
            node=symbol_node(symbol)
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                row['signature']=('async ' if isinstance(node,ast.AsyncFunctionDef) else '')+node.name+'('+ast.unparse(node.args)+')'+(' -> '+ast.unparse(node.returns) if node.returns else '')
            elif isinstance(node,ast.ClassDef):
                row['bases']=[ast.unparse(base) for base in node.bases]
                fields={}
                for item in node.body:
                    if isinstance(item,ast.AnnAssign) and isinstance(item.target,ast.Name):fields[item.target.id]=ast.unparse(item.annotation)
                    elif isinstance(item,ast.Assign):
                        for target in item.targets:
                            if isinstance(target,ast.Name):fields.setdefault(target.id,'untyped')
                    elif isinstance(item,(ast.FunctionDef,ast.AsyncFunctionDef)):
                        # Only direct class methods, no nested function/class attribution.
                        pending=list(item.body)
                        while pending:
                            child=pending.pop()
                            if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.Lambda)):continue
                            targets=[child.target] if isinstance(child,ast.AnnAssign) else child.targets if isinstance(child,ast.Assign) else []
                            for target in targets:
                                if isinstance(target,ast.Attribute) and isinstance(target.value,ast.Name) and target.value.id=='self':
                                    fields[target.attr]=ast.unparse(child.annotation) if isinstance(child,ast.AnnAssign) else fields.get(target.attr,'untyped')
                            pending.extend(ast.iter_child_nodes(child))
                row['fields']=[{'name':name,'annotation':annotation} for name,annotation in sorted(fields.items())]
        except (SyntaxError,ValueError,AttributeError):row['detail_warning']='Definition fragment could not be inspected; indexed source location is retained.'
    return row


def python_import_dependencies(snapshot, cancel=None):
    """Exact local module-name resolution only; conditional imports remain potential."""
    names=defaultdict(list)
    for path in snapshot.hashes:
        if language_for(path)=='python':names[module_name(path)].append(path)
    result=[];warnings=[];root=Path(snapshot.root).resolve()
    for path,digest in sorted(snapshot.hashes.items()):
        checkpoint(cancel)
        if language_for(path)!='python' or digest in {'oversized','unreadable'}:continue
        target=root/path
        if target.is_symlink() or not target.resolve().is_relative_to(root):
            raise ValueError('Project paths changed during architecture review. Review again.')
        raw=target.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:
            raise ValueError('Project changed during architecture review. Review again.')
        try:tree=ast.parse(decode_source(raw,path),filename=path)
        except (SyntaxError,UnicodeError,LookupError):continue
        package=module_name(path).split('.')
        if Path(path).name!='__init__.py':package=package[:-1]
        for node in ast.walk(tree):
            checkpoint(cancel)
            requested=[]
            if isinstance(node,ast.Import):requested=[alias.name for alias in node.names]
            elif isinstance(node,ast.ImportFrom):
                if node.level>len(package)+1:
                    warnings.append(f'Architecture import beyond package root: {path}:{node.lineno}');continue
                prefix=package[:len(package)-node.level+1] if node.level else []
                base='.'.join(prefix+([node.module] if node.module else []))
                if base:requested.append(base)
                requested.extend('.'.join(filter(None,[base,alias.name])) for alias in node.names if alias.name!='*')
            for name in dict.fromkeys(requested):
                choices=names.get(name,[])
                if len(choices)>1:
                    warnings.append(f'Ambiguous local architecture import {name} in {path}:{node.lineno}; no dependency selected.');continue
                if len(choices)==1 and choices[0]!=path:
                    result.append({'from':path,'to':choices[0],'evidence':{
                        'caller':path+':<module>','callee':choices[0]+':<module>','line':node.lineno,
                        'expression':'imports '+name,'kind':'python_module_import','classification':'resolved static','path':path}})
    return result,warnings


def review_architecture(snapshot, cancel=None, progress=lambda value:None):
    progress('Building architecture and LLD inventory…');checkpoint(cancel)
    symbols={}
    for sid,symbol in sorted(snapshot.symbols.items()):
        checkpoint(cancel);symbols[sid]=declaration(symbol)
    modules={}
    for path,digest in sorted(snapshot.hashes.items()):
        if not language_for(path):continue
        modules[path]={'path':path,'language':language_for(path),'hash':digest,'symbols':[], 'outgoing':[], 'incoming':[]}
    for sid,row in symbols.items():
        if row['path'] in modules:modules[row['path']]['symbols'].append(sid)
        parent=sid.rsplit(':',1)[0]+':'+row['qualname'].rsplit('.',1)[0] if '.' in row['qualname'] else None
        row['owner']=parent if parent in symbols else None
    links=[];module_links=defaultdict(list)
    for edge in snapshot.edges:
        checkpoint(cancel)
        if edge['caller'] not in symbols or edge['callee'] not in symbols:continue
        a,b=symbols[edge['caller']]['path'],symbols[edge['callee']]['path']
        item={**edge,'classification':'inferred' if edge['kind'] in INFERRED_KINDS else 'resolved static','path':a}
        links.append(item)
        if a!=b and a in modules and b in modules:module_links[(a,b)].append(item)
    import_links,import_warnings=python_import_dependencies(snapshot,cancel)
    for link in import_links:module_links[(link['from'],link['to'])].append(link['evidence'])
    adjacency={path:set() for path in modules}
    dependencies=[]
    for (a,b),evidence in sorted(module_links.items()):
        resolved=[edge for edge in evidence if edge['classification']=='resolved static']
        dependencies.append({'from':a,'to':b,'classification':'resolved static' if resolved else 'inferred','evidence':evidence})
        modules[a]['outgoing'].append(b);modules[b]['incoming'].append(a)
        if resolved:adjacency[a].add(b)
    findings=[]
    for group in components(adjacency,cancel):
        members=set(group)
        evidence=[edge for edge in dependencies if edge['classification']=='resolved static' and edge['from'] in members and edge['to'] in members]
        findings.append({'kind':'dependency_cycle','title':f'Resolved dependency cycle across {len(group)} files',
                         'explanation':'These files form a strongly connected component in the recorded static graph. Review boundaries before extracting or moving code; a cycle alone is not a defect.',
                         'locations':group,'evidence':evidence})
    for path,module in modules.items():
        checkpoint(cancel)
        if len(module['outgoing'])>=5:
            findings.append({'kind':'coupling','title':f'{path} references {len(module["outgoing"])} local files',
                             'explanation':'Review heuristic: fan-out ≥ 5 distinct indexed files, including inferred relationships. Consider whether this module has several responsibilities.',
                             'locations':[path],'evidence':[e for e in dependencies if e['from']==path]})
    for sid,row in symbols.items():
        if row['kind'] in {'function','async_function','method'} and row['end']-row['start']+1>=80:
            findings.append({'kind':'large_definition','title':f'{row["qualname"]} spans {row["end"]-row["start"]+1} lines',
                             'explanation':'Review heuristic: definition spans ≥ 80 source lines, including comments. Inspect for separable responsibilities; this is not cyclomatic complexity.',
                             'locations':[f'{row["path"]}:{row["start"]}'],'evidence':[sid]})
    progress('Preparing architecture diagrams…');checkpoint(cancel)
    record={'schema_version':2,'snapshot_id':snapshot.id,'revision':snapshot.revision,'hashes':dict(snapshot.hashes),
            'project':Path(snapshot.root).name,'generated_utc':datetime.now(timezone.utc).isoformat(),
            'modules':list(modules.values()),'symbols':list(symbols.values()),'relationships':links,
            'dependencies':dependencies,'findings':findings,'warnings':list(snapshot.warnings)+import_warnings,
            'framework_hints':snapshot.profile.get('frameworks',[]),'capabilities':snapshot.profile.get('capabilities',{}),
            'limits':LIMITS,'summary':{'files':len(modules),'classes':sum(s['kind']=='class' for s in symbols.values()),
             'symbols':len(symbols),'relationships':len(links),'findings':len(findings)}}
    from .design_diagrams import class_edges
    record['design_relationships']=[{'from':a,'to':b,'classification':kind,'evidence_count':count} for a,b,kind,count in class_edges(record)]
    from .feature_flows import analyze_flows
    record['feature_flows']=analyze_flows(snapshot,cancel,progress)
    from .review_quality import build_review
    record['review']=build_review(record,cancel)
    from .design_diagrams import prepare_diagrams
    return prepare_diagrams(record)


def diagram_svg(report, detail=False, limit=48, scope=None, page=0, include_aux=False):
    """Scoped and paginated diagrams. Legacy limit is retained for API compatibility."""
    from .design_diagrams import render,scopes
    if detail and scope is None:
        available=scopes(report,include_aux);scope='lib/app' if 'lib/app' in available else available[0] if available else None
    return render(report,detail,scope,page,include_aux)


def md_text(value):
    return str(value).replace('`',chr(92)+'`').replace('<','&lt;').replace('>','&gt;').replace('\n',' ')


def report_markdown(report):
    from .review_quality import review_markdown
    lines=[f'# Architecture and LLD: {md_text(report["project"])}','',
           f'Snapshot: `{report["snapshot_id"]}` · revision: `{md_text(report["revision"])}`',
           '','Generated from saved, indexed source. No repository code was executed.','',
           '![HLD · packages and dependencies](architecture.svg)','', '![LLD · classes and members](lld.svg)','', '[Open the paginated LLD diagram index](lld-index.md)','',
           review_markdown(report),'',
           '## Detailed source records','',
           'The complete declaration inventory, signatures, dependency edges, raw heuristic candidates and diagnostic occurrences are preserved in `report.json`. The code structure diagram book is linked above.','']
    lines+=['## Framework declarations','']+[f'- {md_text(f["name"])} · `{md_text(f["path"])}` · {md_text(f.get("note","declaration hint only"))}' for f in report['framework_hints']]
    lines+=['','## Limits','']+['- '+v for v in report['limits']]
    return '\n'.join(lines)+'\n'


def export_bundle(report, snapshot, destination, cancel=None):
    checkpoint(cancel)
    if snapshot.id!=report['snapshot_id'] or revision(Path(snapshot.root))!=report['revision'] or fingerprint(Path(snapshot.root),cancel)!=report['hashes']:
        raise ValueError('Project changed. Generate a fresh architecture review before exporting.')
    md=report_markdown(report);architecture=diagram_svg(report);lld=diagram_svg(report,True)
    flow_rows=report.get('feature_flows',{}).get('flows',[])
    if flow_rows:
        from .feature_flows import design_model,model_svg
        architecture=model_svg(design_model(report))
        representative=max(flow_rows,key=lambda f:(len(f['matches'])==1,bool(f['updates']),any((m['handler_detail'] or {}).get('data') for m in f['matches'])))
        lld=model_svg(design_model(report,representative))
        md=md.replace('![HLD · packages and dependencies](architecture.svg)','![System overview · compatible source request paths](architecture.svg)').replace('![LLD · classes and members](lld.svg)','![Representative implementation flow · source candidates](lld.svg)\n\n[Browse every extracted feature flow](flows.md)').replace('[Open the paginated LLD diagram index]','[Open the separate code structure index]')
    from .design_diagrams import book
    pages,diagram_index=book(report,cancel);checkpoint(cancel)
    root=Path(tempfile.mkdtemp(prefix='ChangeLens-architecture-',dir=destination))
    (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (root/'report.md').write_text(md,encoding='utf-8')
    (root/'architecture.svg').write_text(architecture,encoding='utf-8')
    (root/'lld.svg').write_text(lld,encoding='utf-8')
    (root/'lld-index.md').write_text(diagram_index,encoding='utf-8')
    (root/'lld').mkdir()
    for name,svg in pages.items():(root/'lld'/name).write_text(svg,encoding='utf-8')
    if report.get('feature_flows',{}).get('flows'):
        from .feature_flows import design_model,model_svg,flows_markdown
        (root/'systems.svg').write_text(model_svg(design_model(report)),encoding='utf-8')
        (root/'flows.md').write_text(flows_markdown(report),encoding='utf-8')
        (root/'flows').mkdir()
        for flow in report['feature_flows']['flows']:
            checkpoint(cancel)
            (root/'flows'/(flow['id']+'.svg')).write_text(model_svg(design_model(report,flow)),encoding='utf-8')
    return root


if __name__ == '__main__':
    import argparse
    from .core import index_repository, app_dir
    parser=argparse.ArgumentParser(description='Offline architecture and implementation LLD review; never executes project code.')
    parser.add_argument('repository',type=Path)
    parser.add_argument('--output',type=Path,default=app_dir()/'reports')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    snapshot=index_repository(args.repository)
    print(export_bundle(review_architecture(snapshot),snapshot,args.output))
