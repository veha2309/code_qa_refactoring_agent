"""Dart declarations and straightforward Flutter composition references."""
from dataclasses import dataclass
from pathlib import PurePosixPath
import posixpath
import re
from .core import checkpoint


@dataclass
class DartFunction:
    sig: object
    body: object
    type: str='dart_function'
    @property
    def start_byte(self):return self.sig.start_byte
    @property
    def end_byte(self):return self.body.end_byte
    @property
    def start_point(self):return self.sig.start_point
    @property
    def end_point(self):return self.body.end_point
    @property
    def named_children(self):return [self.sig,self.body]
    @property
    def children(self):return self.named_children


def declaration_at(root,start,end):
    pending=[root]
    while pending:
        parent=pending.pop();children=parent.named_children
        for index,node in enumerate(children[:-1]):
            body=children[index+1]
            if node.type in {'function_signature','method_signature'} and body.type=='function_body' and node.start_byte==start and body.end_byte==end:return DartFunction(node,body)
        pending.extend(child for child in children if child.start_byte<=start and child.end_byte>=end)
    raise ValueError('Replace exactly the focused Dart function or method, without extra declarations.')


def extract(unit,root,text,field,add,scope):
    unit.dart_imports=[];unit.dart_widgets=set()
    def descendants(node,kind):
        pending=[node]
        while pending:
            child=pending.pop()
            if child.type==kind:yield child
            pending.extend(reversed(child.named_children))
    def parameters(node):
        return {text(field(n,'name')) for n in descendants(node,'formal_parameter') if field(n,'name') is not None}
    def scan(node,owner,lexical,callback=False):
        if node.type=='function_expression':
            inner=lexical+'.$callback@'+str(node.start_byte);scope(inner,lexical)['bound'].update(parameters(node));lexical=inner;callback=True
        if node.type in {'initialized_variable_definition','initialized_identifier'}:
            name=field(node,'name') or next((c for c in node.named_children if c.type=='identifier'),None)
            if name is not None:unit.scopes[lexical]['bound'].add(text(name))
        if node.type in {'const_object_expression','new_expression'}:
            names=[text(c) for c in node.named_children if c.type in {'type_identifier','identifier','scoped_identifier'}]
            if names:unit.calls.append((owner,'.'.join(names),node.start_point.row+1,lexical,'constructor_reference'))
        children=node.named_children
        for index,child in enumerate(children):
            if child.type!='identifier' or index+1>=len(children) or children[index+1].type!='selector':continue
            expression=text(child);argument=None;last=child
            for item in children[index+1:]:
                if item.type!='selector':break
                last=item;arg=next(descendants(item,'argument_part'),None)
                if arg is not None:argument=arg;break
                expression+=text(item).replace('?.','.')
            if argument is None:continue
            literal=next(descendants(argument,'string_literal'),None)
            is_test=unit.path.endswith('_test.dart') and expression in {'test','testWidgets'} and literal is not None and any(item['uri'].startswith(('package:test/','package:flutter_test/')) for item in unit.dart_imports)
            if is_test:
                label=text(literal).strip('\"\'');span=DartFunction(child,last)
                symbol=add(span,f'{expression}[{label}]@{child.start_point.row+1}','function',lexical,True)
                scope(symbol.id,lexical)['bound'].update(parameters(argument))
                for callback_node in descendants(argument,'function_expression'):
                    for body in callback_node.named_children:
                        if body.type=='function_expression_body':scan(body,symbol.id,symbol.id)
                continue
            unit.calls.append((owner,expression,child.start_point.row+1,lexical,'callback_reference' if callback else 'static_reference'))
        for child in children:
            # Test callback ownership is recorded above instead of duplicated as main().
            if node.type=='selector' and any(c.type=='argument_part' for c in children):
                parent=node.parent;previous=node.prev_named_sibling
                if previous is not None and text(previous) in {'test','testWidgets'} and unit.path.endswith('_test.dart'):return
            scan(child,owner,lexical,callback)
    def declarations(parent,owner):
        children=parent.named_children;index=0
        while index<len(children):
            node=children[index]
            if node.type=='import_or_export':
                value=text(node);match=re.search(r"(?:import|export|part)\s+['\"]([^'\"]+)['\"]",value)
                if match:
                    uri=match.group(1);alias=re.search(r'\bas\s+(\w+)',value)
                    show=re.search(r'\bshow\s+([^;]+)',value);hide=re.search(r'\bhide\s+([^;]+)',value)
                    unit.dart_imports.append({'uri':uri,'prefix':alias.group(1) if alias else '', 'export':value.lstrip().startswith('export'), 'show':set(re.findall(r'\w+',show.group(1))) if show else set(),'hide':set(re.findall(r'\w+',hide.group(1))) if hide else set()});unit.imports.append(uri)
            elif node.type in {'class_definition','mixin_declaration','enum_declaration','extension_declaration'}:
                name=field(node,'name') or next((c for c in node.named_children if c.type=='identifier'),None)
                if name is not None:
                    symbol=add(node,text(name),'class',owner)
                    if re.search(r'\bextends\s+(?:StatelessWidget|StatefulWidget|State\s*<)',text(node).split('{',1)[0]):unit.dart_widgets.add(symbol.id)
                    body=field(node,'body') or next((c for c in node.named_children if c.type=='class_body'),None)
                    if body is not None:declarations(body,symbol.id)
            elif node.type in {'function_signature','method_signature'} and index+1<len(children) and children[index+1].type=='function_body':
                sig=node if node.type=='function_signature' else next(descendants(node,'function_signature'),None)
                name=field(sig,'name') if sig is not None else None
                if name is not None:
                    body=children[index+1];symbol=add(DartFunction(node,body),text(name),'function',owner)
                    scope(symbol.id,owner)['bound'].update(parameters(sig));scan(body,symbol.id,symbol.id);index+=1
            index+=1
    declarations(root,unit.module)
    unit.warnings.append(f'{unit.path}: Dart references are static; Flutter build/createState links are inferences. Dynamic dispatch, navigation and dependency injection may be unresolved.')


def link(root,units,profile,cancel=None):
    darts={p:u for p,u in units.items() if u.language=='dart'};edges=[];warnings=[]
    def target(unit,uri):
        if uri.startswith('dart:'):return None
        if uri.startswith('package:'):
            package,_,tail=uri[8:].partition('/')
            candidates=[posixpath.join(posixpath.dirname(path),'lib',tail) for path,data in profile.get('manifests',{}).items() if data.get('package_name')==package]
        else:candidates=[posixpath.normpath(posixpath.join(posixpath.dirname(unit.path),uri))]
        found=[path for path in candidates if path in darts]
        return found[0] if len(found)==1 else None
    def exported(path,name,seen=None):
        seen=set() if seen is None else seen
        if path in seen or len(seen)>64 or name.startswith('_'):return set()
        unit=darts[path];found=set(unit.scopes[unit.module]['defs'].get(name,set()))
        for item in unit.dart_imports:
            if not item['export'] or item['show'] and name not in item['show'] or name in item['hide']:continue
            path2=target(unit,item['uri'])
            if path2:found.update(exported(path2,name,seen|{path}))
        return found
    def add(caller,callee,line,expression,kind):edges.append({'caller':caller,'callee':callee,'line':line,'expression':expression,'kind':kind})
    for path,unit in darts.items():
        checkpoint(cancel)
        for item in unit.dart_imports:
            other=target(unit,item['uri'])
            if other:add(unit.module,darts[other].module,1,'Dart import/export '+item['uri'],'module_import')
            elif not item['uri'].startswith(('package:','dart:')):warnings.append(f'Unresolved Dart library {item["uri"]} in {path}')
        for caller,expression,line,lexical,kind in unit.calls:
            parts=expression.split('.');name=parts[-1];found=set();current=lexical;shadowed=False
            if len(parts)>1:
                while current:
                    info=unit.scopes.get(current,{})
                    if parts[0] in info.get('bound',set()):shadowed=True;break
                    current=info.get('parent')
                current=lexical
            if len(parts)==1:
                while current:
                    info=unit.scopes.get(current,{})
                    if name in info.get('defs',{}):found.update(info['defs'][name]);break
                    if name in info.get('bound',set()):shadowed=True;break
                    current=info.get('parent')
            if not found and not shadowed:
                for item in unit.dart_imports:
                    if item['export'] or item['prefix']!=(parts[0] if len(parts)==2 else '') or len(parts)>2:continue
                    if item['show'] and name not in item['show'] or name in item['hide']:continue
                    other=target(unit,item['uri'])
                    if other:found.update(exported(other,name))
            if len(found)==1:add(caller,next(iter(found)),line,expression,kind)
            elif expression:warnings.append(f'Unresolved Dart reference {path}:{line}: {expression} (SDK/external, dynamic, shadowed or ambiguous)')
        for symbol in unit.symbols:
            parent=unit.scopes.get(symbol.id,{}).get('parent')
            if parent in unit.dart_widgets and symbol.name in {'build','createState'}:add(parent,symbol.id,symbol.start,'Flutter '+symbol.name+' entry point (composition inference)','flutter_build')
    return edges,warnings
