"""Conservative context packing. Large rewrites use exact visible snippet edits."""
import math
import re


def estimate_tokens(text):
    # Deliberately conservative for source, Unicode and JSON escapes; not a tokenizer.
    return math.ceil(len(text.encode('utf-8'))/2)+16


def fit_text(text,budget,from_end=False):
    if budget<=16:return ''
    if estimate_tokens(text)<=budget:return text
    raw=text.encode('utf-8');raw=raw[-(budget-16)*2:] if from_end else raw[:(budget-16)*2]
    return raw.decode('utf-8','ignore')


def excerpt(code,budget,focus=0):
    if estimate_tokens(code)<=budget:return code,{'included_lines':[[1,len(code.splitlines())]],'omitted':False,'characters':len(code)}
    lines=code.splitlines(True);focus=max(0,min(len(code),focus));line=code[:focus].count('\n')
    first=max(0,line-12);last=min(len(lines),line+18)
    while last>first+1 and estimate_tokens(''.join(lines[first:last]))>budget:
        if line-first>last-line:first+=1
        else:last-=1
    value=''.join(lines[first:last]);value=fit_text(value,budget)
    return value,{'included_lines':[[first+1,last]],'omitted':True,'characters':len(code)}


def snippet_edits(code,visible,edits):
    if not isinstance(edits,list) or not 1<=len(edits)<=6:raise ValueError('The model must return one to six exact snippet edits.')
    changes=[]
    for edit in edits:
        if not isinstance(edit,dict) or not isinstance(edit.get('old'),str) or not isinstance(edit.get('new'),str):raise ValueError('Invalid snippet edit.')
        old,new=edit['old'],edit['new']
        if len(old)<8 or old not in visible or code.count(old)!=1:raise ValueError('Snippet edit is ambiguous or outside the supplied context. No source change was accepted.')
        start=code.index(old);changes.append((start,start+len(old),new))
    changes.sort()
    if any(a[1]>b[0] for a,b in zip(changes,changes[1:])):raise ValueError('Snippet edits overlap.')
    for start,end,new in reversed(changes):code=code[:start]+new+code[end:]
    return code


def related_context(snapshot,symbol,analysis=None,budget=768):
    """Pack referenced definitions before callers, tests and broad type context."""
    if symbol is None or budget < 72:
        return ''
    from .context_evidence import context_files, definition_fragments, saved_source

    names = set(re.findall(r'[^\W\d]\w*', symbol.source))
    related = {}
    records = []
    seen = set()

    def add(rank, path, start, end, label, source):
        key = path, start, end, source.strip()
        if key in seen or not source.strip():
            return
        seen.add(key)
        fragment = fit_text(source.strip(), 135)
        location = f'{path}:{start}' + (f'–{end}' if end != start else '')
        qualifier = ' (partial)' if fragment != source.strip() else ''
        records.append((rank, f'{location} [{label}]{qualifier}\n{fragment}'))

    for edge in snapshot.edges:
        outgoing = edge['caller'] == symbol.id
        if outgoing or edge['callee'] == symbol.id:
            sid = edge['callee'] if outgoing else edge['caller']
            if sid == symbol.id:
                continue
            rank = 1 if outgoing else 5
            previous = related.get(sid)
            if previous is None or rank < previous[0]:
                related[sid] = rank, edge['kind']

    linked = context_files(snapshot, symbol, names, snapshot.edges)
    dependency_paths = list(linked)[:8]
    omitted = len(linked) - len(dependency_paths)
    for path in [*dependency_paths, symbol.path]:
        label, wanted = linked.get(path, ('same-file declaration', names))
        source = saved_source(snapshot, path)
        if source is None:
            omitted += 1
            continue
        for start, end, fragment in definition_fragments(path, source, wanted):
            if path == symbol.path and symbol.start <= start and end <= symbol.end:
                continue
            add(0 if path != symbol.path else 2, path, start, end, label, fragment)

    for sid,s in snapshot.symbols.items():
        if sid == symbol.id or s.kind == 'module':
            continue
        if sid in related:
            rank, label = related[sid]
            add(6 if s.is_test else rank, s.path, s.start, s.end, label, s.source)
        elif s.path in dependency_paths and s.name in linked[s.path][1] and not s.is_test:
            add(3 if s.kind != 'class' else 5, s.path, s.start, s.end,
                'matching declaration, ' + linked[s.path][0], s.source)
        elif s.path == symbol.path and s.kind == 'class':
            add(6, s.path, s.start, s.end, 'same-file type', s.source)

    unresolved = [warning for warning in snapshot.warnings
                  if warning.startswith('Unresolved local module ') and f' imported by {symbol.path}:' in warning]
    records.extend((4, warning) for warning in unresolved[:2])
    omitted += max(0, len(unresolved) - 2)
    for flow in (analysis or {}).get('flows',[])+(analysis or {}).get('server_flows',[]):
        matched=[s for s in flow.get('steps',[]) if s['source']['path']==symbol.path and symbol.start<=s['source']['line']<=symbol.end]
        if matched:
            records.append((4, 'Feature: '+flow.get('screen',flow['title'])+' / '+flow['method']+' '+flow['url']+' (candidate route)'))

    rows = ['Related saved-source excerpts. Static links may be incomplete.']
    footer = 'Omitted context records: {}.'
    reserved_footer = footer.format(omitted + len(records))
    for _, chunk in sorted(records, key=lambda record: record[0]):
        if estimate_tokens('\n\n'.join([*rows, chunk, reserved_footer])) <= budget:
            rows.append(chunk)
        else:
            omitted += 1
    return '\n\n'.join([*rows, footer.format(omitted)])
