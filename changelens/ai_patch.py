"""Validate bounded, exact-span model proposals for Tree-sitter languages."""
import difflib
import json
from pathlib import Path
from .core import decode_source,ensure_fresh
from .syntax import grammar,parse_unit


def exact_node(path,source,start,end):
    from tree_sitter import Parser
    from .languages import language_for
    tree=Parser(grammar(language_for(path))).parse(source.encode('utf-8'))
    if language_for(path)=='dart':
        from .dart_adapter import declaration_at
        return declaration_at(tree.root_node,start,end)
    pending=[tree.root_node]
    while pending:
        node=pending.pop()
        if node.start_byte==start and node.end_byte==end and node.type in {'function_declaration','generator_function_declaration','method_definition','variable_declarator','method_declaration','constructor_declaration','function_item'}:return node
        pending.extend(child for child in node.named_children if child.start_byte<=start and child.end_byte>=end)
    raise ValueError('The proposal must replace exactly the focused declaration, without surrounding code or extra declarations.')


def signature(node,raw):
    if node.type=='dart_function':
        tokens=[];pending=[node.sig]
        while pending:
            child=pending.pop()
            if 'comment' in child.type:continue
            if child.children:pending.extend(reversed(child.children))
            else:tokens.append((child.type,raw[child.start_byte:child.end_byte].decode('utf-8')))
        tokens.extend((child.type,raw[child.start_byte:child.end_byte].decode('utf-8')) for child in node.body.children if child.type in {'async','sync','*'})
        return tokens
    owner=node
    if node.type=='variable_declarator':owner=node.child_by_field_name('value')
    body=owner.child_by_field_name('body') if owner else None
    if body is None:raise ValueError('Select a function or method with a body. This declaration cannot be rewritten safely.')
    tokens=[];pending=[node]
    while pending:
        child=pending.pop()
        if child==body or 'comment' in child.type:continue
        if not child.children:tokens.append((child.type,raw[child.start_byte:child.end_byte].decode('utf-8')))
        else:pending.extend(reversed(child.children))
    return tokens


def dependencies(node,raw):
    result=[];pending=[node]
    while pending:
        child=pending.pop()
        if child.type in {'import_statement','import_declaration','using_directive','use_declaration','import_expression'} or child.type=='call_expression' and raw[(fn:=child.child_by_field_name('function')).start_byte:fn.end_byte] in {b'import',b'require'}:
            result.append(raw[child.start_byte:child.end_byte])
        pending.extend(child.named_children)
    return sorted(result)


def foreign_rewrite_patch(snapshot,symbol,answer):
    ensure_fresh(snapshot)
    value=json.loads(answer)
    if not isinstance(value,dict) or not isinstance(value.get('code'),str):raise ValueError('The model must return a JSON code proposal.')
    proposed=value['code'].strip()
    if not proposed or len(proposed)>5000:raise ValueError('The model proposal was empty or too large. Select a smaller declaration.')
    before=decode_source((Path(snapshot.root)/symbol.path).read_bytes(),symbol.path).replace('\r\n','\n')
    # Index byte spans refer to decoded source with its original newlines.
    current=parse_unit(symbol.path,before);matches=[s for s in current.symbols if s.id==symbol.id and s.start==symbol.start and s.source==symbol.source.replace('\r\n','\n')]
    selected=matches[0] if len(matches)==1 else None
    if not selected or selected.start_byte<0 or selected.kind!='function':raise ValueError('Select a supported named function, arrow declaration or method first.')
    raw=before.encode('utf-8');start,end=selected.start_byte,selected.end_byte
    old=exact_node(symbol.path,before,start,end)
    after_raw=raw[:start]+proposed.encode('utf-8')+raw[end:];after=after_raw.decode('utf-8')
    try:parse_unit(symbol.path,after)
    except SyntaxError as exc:raise ValueError('The proposed code failed syntax validation: '+str(exc)) from exc
    new=exact_node(symbol.path,after,start,start+len(proposed.encode('utf-8')))
    if old.type!=new.type or signature(old,raw)!=signature(new,after_raw):raise ValueError('The proposal changed the declaration name, signature, modifiers or public shape. It was rejected.')
    if dependencies(old,raw)!=dependencies(new,after_raw):raise ValueError('The proposal changed imports or dependency loading. It was rejected.')
    if after==before:raise ValueError('The model did not propose a change.')
    diff=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+symbol.path,tofile='b/'+symbol.path))
    return {'snapshot':snapshot.id,'path':symbol.path,'operation':'ai_rewrite','old':symbol.name,'new':'ai_suggestion',
        'files':[{'path':symbol.path,'before':before,'after':after,'diff':diff}],'diff':diff,'syntax_validation':'passed','tests':'not run',
        'explanation':str(value.get('explanation',''))[:3000],
        'limitations':'Exact declaration span and signature checked with the bundled syntax parser. Type checking, runtime behavior and tests were not checked.'}
