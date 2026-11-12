"""Scoped, paginated implementation diagrams with connectors outside cards."""
from collections import defaultdict, deque
from html import escape
from pathlib import PurePosixPath
import math
import re
import textwrap
from functools import lru_cache

PAGE_SIZE=10


class DiagramReport(dict):
    """Report with transient indexes; attributes never enter JSON exports."""
    pass


def prepare_diagrams(report):
    if isinstance(report,DiagramReport):return report
    result=DiagramReport(report);result.scope_groups={False:defaultdict(list),True:defaultdict(list)}
    for row in result['symbols']:
        if not (row['kind']=='class' or row['kind'] in {'function','async_function','method'} and not row.get('owner')):continue
        scope=scope_for(row['path']);result.scope_groups[True][scope].append(row)
        if not auxiliary(row['path']) and not row.get('is_test'):result.scope_groups[False][scope].append(row)
    result.all_candidates={flag:[row for rows in groups.values() for row in rows] for flag,groups in result.scope_groups.items()}
    return result


@lru_cache(maxsize=32768)
def auxiliary(path):
    p=PurePosixPath(path);parts=set(p.parts)
    return bool(parts & {'test','tests','__tests__','generated','.dart_tool'}) or p.name.lower().startswith('generated') or p.name.endswith(('.g.dart','.freezed.dart'))


@lru_cache(maxsize=32768)
def scope_for(path):
    p=PurePosixPath(path).parent;parts=p.parts
    if len(parts)>=3 and parts[0] in {'lib','src'} and parts[1] in {'features','core','shared'}:return '/'.join(parts[:3])
    return p.as_posix()


def candidates(report,scope=None,include_aux=False):
    indexed=prepare_diagrams(report)
    return indexed.all_candidates[include_aux] if scope is None else indexed.scope_groups[include_aux].get(scope,[])


def scopes(report,include_aux=False):return sorted(prepare_diagrams(report).scope_groups[include_aux])


def ordered_records(report,scope,include_aux=False):
    records=candidates(report,scope,include_aux);lookup={s['id']:s for s in records};adj={sid:set() for sid in lookup}
    for a,b,kind,count in class_edges(report):
        if a in adj and b in adj:adj[a].add(b);adj[b].add(a)
    result=[];seen=set()
    for start in sorted(adj,key=lambda n:(-len(adj[n]),n)):
        if start in seen:continue
        queue=deque([start]);seen.add(start)
        while queue:
            sid=queue.popleft();result.append(lookup[sid])
            for target in sorted(adj[sid],key=lambda n:(-len(adj[n]),n)):
                if target not in seen:seen.add(target);queue.append(target)
    return result


def class_edges(report):
    if 'design_relationships' in report:return [(e['from'],e['to'],e['classification'],e['evidence_count']) for e in report['design_relationships']]
    lookup={s['id']:s for s in report['symbols']};containers={}
    for sid,row in lookup.items():
        seen=set()
        while row and row.get('owner') and row['id'] not in seen:
            seen.add(row['id']);row=lookup.get(row['owner'],row)
        containers[sid]=row['id'] if row else sid
    counts=defaultdict(int);resolved=set()
    for edge in report['relationships']:
        a,b=containers.get(edge['caller']),containers.get(edge['callee'])
        if a and b and a!=b:
            counts[a,b]+=1
            if edge['classification']!='inferred':resolved.add((a,b))
    result=[(a,b,'resolved static' if (a,b) in resolved else 'inferred',n) for (a,b),n in sorted(counts.items())]
    # Type-name links are explicitly weaker than resolved call references.
    by_name=defaultdict(list)
    for row in report['symbols']:
        if row['kind']=='class':by_name[row['name']].append(row)
    imported={(e['from'],e['to']) for e in report['dependencies'] if e['classification']!='inferred'}
    existing={(a,b) for a,b,_,_ in result}
    for row in report['symbols']:
        if row['kind']!='class':continue
        names=set()
        for field in row.get('fields',[]):names.update(re.findall(r'\b[A-Za-z_]\w*\b',field['annotation']))
        for name in sorted(names):
            possible=[s for s in by_name[name] if s['path']==row['path'] or (row['path'],s['path']) in imported]
            if len(possible)==1:
                target=possible[0]['id'];pair=(row['id'],target)
                if target!=row['id'] and pair not in existing:
                    result.append((*pair,'declared type (unverified)',1));existing.add(pair)
    return result


def page_count(report,scope=None,include_aux=False):
    count=len(scopes(report,include_aux)) if scope is None else len(candidates(report,scope,include_aux))
    return max(1,math.ceil(count/PAGE_SIZE))


def _label(value,n=53):return value if len(value)<=n else value[:n-1]+'…'


def render(report,detail=False,scope=None,page=0,include_aux=False,focus=None):
    report=prepare_diagrams(report)
    overview=scope is None
    members=defaultdict(list)
    for row in report['symbols']:
        if row.get('owner'):members[row['owner']].append(row)
    if overview:
        groups=scopes(report,include_aux);records=[]
        for group in groups:
            items=candidates(report,group,include_aux);paths={s['path'] for s in items}
            records.append({'id':group,'title':group,'subtitle':f'{len(items)} classes / top-level functions · {len(paths)} files',
                'fields':[], 'operations':[s['name'] for s in sorted(items,key=lambda x:x['name'])[:5]],'extra':max(0,len(items)-5),'group':True})
        counts=defaultdict(int);resolved=set()
        for edge in report['dependencies']:
            a,b=scope_for(edge['from']),scope_for(edge['to'])
            if a!=b and a in groups and b in groups and (include_aux or not auxiliary(edge['from']) and not auxiliary(edge['to'])):
                counts[a,b]+=len(edge['evidence'])
                if edge['classification']!='inferred':resolved.add((a,b))
        edges=[(a,b,'resolved static' if (a,b) in resolved else 'inferred',n) for (a,b),n in sorted(counts.items())]
    else:
        records=[]
        for s in ordered_records(report,scope,include_aux):
            if focus and s['id']!=focus:continue
            methods=members[s['id']];ops=[m.get('signature') or m['name']+'(…) [signature unavailable]' for m in sorted(methods,key=lambda m:m['start'])]
            if not methods and s.get('signature'):ops=[s['signature']]
            ops=s.get('constructors',[])+ops
            records.append({'id':s['id'],'title':s['name'],'subtitle':s['path']+':'+str(s['start']),
                'fields':[f"{f['name']}: {f['annotation']}" for f in s.get('fields',[])][:None if focus else 4],
                'operations':(s.get('enum_values') or ops)[:None if focus else 5],'declaration_kind':s.get('declaration_kind',s['kind']),'extra':0 if focus else max(0,len(ops)-5)+max(0,len(s.get('fields',[]))-4),
                'bases':s.get('bases',[]),'group':False})
        edges=class_edges(report)
    total=len(records);pages=max(1,math.ceil(total/PAGE_SIZE));page=max(0,min(page,pages-1));chosen=records[page*PAGE_SIZE:(page+1)*PAGE_SIZE]
    ids={r['id'] for r in chosen};visible=[e for e in edges if e[0] in ids and e[1] in ids];outside=sum((a in ids)!=(b in ids) for a,b,_,_ in edges)
    # Two columns, variable card heights, dedicated connector lanes in the center/outside gutters.
    positions={};bottom=[130,130];cardw=405
    for index,row in enumerate(chosen):
        row['field_lines']=[part for value in row['fields'] for part in textwrap.wrap(value,width=49,subsequent_indent='  ')]
        row['operation_lines']=[part for value in row['operations'] for part in textwrap.wrap(value,width=49,subsequent_indent='  ')]
        col=index%2;h=120+(len(row['field_lines'])+len(row['operation_lines'])+bool(row.get('bases'))+bool(row['extra']))*20
        positions[row['id']]=(58+col*565,bottom[col],cardw,h,col);bottom[col]+=h+50
    width=1110;height=max(380,max(bottom)+65)
    esc=lambda value:escape(str(value))
    title='HLD · package overview' if overview else 'LLD · '+(chosen[0]['title'] if focus and chosen else scope)
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#171d25"/>',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#83a5a9"/></marker></defs>',
        f'<text x="58" y="38" fill="#e0e9e7" font-family="sans-serif" font-size="22">{esc(_label(title,85))}</text>',
        f'<text x="58" y="64" fill="#9cafbd" font-family="sans-serif" font-size="12">{esc(report["project"])} · page {page+1}/{pages} · {len(chosen)}/{total} items in this scope · snapshot {esc(report["snapshot_id"])}</text>',
        '<text x="58" y="88" fill="#9cafbd" font-family="sans-serif" font-size="12">Caller → dependency · solid: resolved reference · dashed: inferred / declared type · package groups follow source directories</text>']
    for i,(a,b,kind,count) in enumerate(visible):
        x,y,w,h,c=positions[a];u,v,ww,hh,d=positions[b]
        if c!=d:
            sx=x+w if c==0 else x;tx=u if d==1 else u+ww;lane=490+(i%12)*7
        else:
            sx=x if c==0 else x+w;tx=u if c==0 else u+ww;lane=(22+(i%5)*5) if c==0 else (1060+(i%5)*6)
        sy=y+55;ty=v+55;dash=' stroke-dasharray="6 5"' if kind!='resolved static' else ''
        parts.append(f'<path d="M {sx} {sy} H {lane} V {ty} H {tx}" fill="none" stroke="#6e9298" stroke-width="1.35"{dash} marker-end="url(#arrow)"><title>{esc(a)} → {esc(b)} · {count} evidence records · {esc(kind)}</title></path>')
    for row in chosen:
        x,y,w,h,c=positions[row['id']];accent='#89bdb1' if row['group'] else '#9baed2'
        parts.append(f'<g><title>{esc(row["id"])}</title><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="#222c37" stroke="#415664"/>')
        parts.append(f'<rect x="{x}" y="{y+12}" width="3" height="34" rx="1" fill="{accent}"/>')
        def line(value,yy,color='#c9d9df',size=12):
            parts.append(f'<text x="{x+16}" y="{yy}" fill="{color}" font-family="monospace" font-size="{size}">{esc(_label(value,50 if size==12 else 37))}</text>')
        line(row['title']+('' if row['group'] else '  «'+row.get('declaration_kind','class')+'»'),y+29,'#e2ece8',15);line(row['subtitle'],y+50,'#98adbb',11)
        yy=y+75
        if row.get('bases'):line('extends / implements: '+', '.join(row['bases']),yy,'#b6a7d4');yy+=20
        if row['fields']:
            for value in row['field_lines']:line(value,yy);yy+=20
            parts.append(f'<path d="M {x+14} {yy-9} H {x+w-14}" stroke="#3b4c59"/>');yy+=10
        for value in row['operation_lines']:line(value,yy);yy+=20
        if not row['operations'] and not row['fields']:line('No indexed member details',yy,'#98adbb')
        if row['extra']:line(f'+ {row["extra"]} more members in report.json',yy,'#98adbb')
        parts.append('</g>')
    if not chosen:parts.append('<text x="58" y="160" fill="#c9d9df" font-family="sans-serif">No declarations in this scope. Enable tests/generated or choose another package.</text>')
    parts.append(f'<text x="58" y="{height-38}" fill="#9cafbd" font-family="sans-serif" font-size="12">{len(visible)} deduplicated connections on this page · {outside} connections leave this page/scope · complete evidence in report.json</text>')
    parts.append(f'<text x="58" y="{height-18}" fill="#9cafbd" font-family="sans-serif" font-size="12">Tests/generated files {("included" if include_aux else "excluded from diagrams only")} · choose a package for member-level LLD · see lld-index.md in exports</text></svg>')
    return ''.join(parts)


def book(report,cancel=None):
    from .core import checkpoint
    pages={};index=['# LLD diagram index','', 'Package membership follows source directories; labels are not inferred runtime responsibilities. Tests/generated files are excluded from diagrams; all indexed records remain in report.json.','']
    overview_pages=page_count(report)
    for page in range(overview_pages):
        checkpoint(cancel);name=f'overview-{page+1}.svg';pages[name]=render(report,True,page=page)
        index.append(f'- [Project overview {page+1}](lld/{name})')
    for number,group in enumerate(scopes(report),1):
        for page in range(page_count(report,group)):
            checkpoint(cancel);name=f'package-{number:03d}-{page+1}.svg';pages[name]=render(report,True,group,page)
            index.append(f'- [{escape(group)} · page {page+1}](lld/{name})')
    index+=['','## Complete class / function details','']
    for number,row in enumerate(sorted(candidates(report),key=lambda r:r['id']),1):
        checkpoint(cancel);name=f'detail-{number:04d}.svg';pages[name]=render(report,True,scope_for(row['path']),focus=row['id'])
        index.append(f'- [{escape(row["qualname"])} · {escape(row["path"])}](lld/{name})')
    return pages,'\n'.join(index)+'\n'
