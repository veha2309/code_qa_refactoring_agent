"""Bundled Tree-sitter syntax adapters. Repository code is never loaded as code."""
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
import re

from .languages import language_for


@lru_cache(maxsize=9)
def grammar(language):
    from tree_sitter import Language
    if language=="javascript":
        import tree_sitter_javascript as module
        capsule=module.language()
    elif language in {"typescript","tsx"}:
        import tree_sitter_typescript as module
        capsule=module.language_tsx() if language=="tsx" else module.language_typescript()
    elif language=="java":
        import tree_sitter_java as module
        capsule=module.language()
    elif language=="csharp":
        import tree_sitter_c_sharp as module
        capsule=module.language()
    elif language=="go":
        import tree_sitter_go as module
        capsule=module.language()
    elif language=="rust":
        import tree_sitter_rust as module
        capsule=module.language()
    elif language=='dart':
        import tree_sitter_dart as module
        capsule=module.language()
    else:raise ValueError("No syntax adapter for "+language)
    return Language(capsule)


@dataclass
class Unit:
    path: str
    source: str
    language: str
    symbols: list = field(default_factory=list)
    calls: list = field(default_factory=list)
    scopes: dict = field(default_factory=dict)
    exports: dict = field(default_factory=dict)
    stars: list = field(default_factory=list)
    imports: list = field(default_factory=list)
    namespace: str = ""
    warnings: list = field(default_factory=list)

    @property
    def module(self):return self.path+":<module>"


def parse_unit(path,source):
    from tree_sitter import Parser
    from .core import Symbol
    language=language_for(path); raw=source.encode("utf-8"); tree=Parser(grammar(language)).parse(raw)
    if tree.root_node.has_error:
        pending=[tree.root_node]; line=1
        while pending:
            node=pending.pop()
            if node.is_error or node.is_missing:line=node.start_point.row+1;break
            pending.extend(reversed(node.named_children))
        raise SyntaxError(f"{language} syntax error near line {line}")
    unit=Unit(path,source,language)
    def text(node):return raw[node.start_byte:node.end_byte].decode("utf-8") if node is not None else ""
    def field(node,name):return node.child_by_field_name(name)
    def scope(sid,parent):
        return unit.scopes.setdefault(sid,{"parent":parent,"defs":{},"bindings":{},"bound":set(),"reassigned":set()})
    scope(unit.module,None)
    module_symbol=Symbol(unit.module,path,Path(path).name,"<module>","module",1,max(1,len(source.splitlines())),source)
    unit.symbols.append(module_symbol); stripped_bodies=[]
    def add(node,name,kind,parent,is_test=False):
        prefix=parent.split(":",1)[1] if parent!=unit.module else ""
        qual=".".join(filter(None,[prefix,name])); sid=path+":"+qual
        symbol=Symbol(sid,path,name,qual,kind,node.start_point.row+1,node.end_point.row+1,text(node),is_test)
        symbol.start_byte=node.start_byte;symbol.end_byte=node.end_byte
        unit.symbols.append(symbol)
        current=scope(parent,None); current["defs"].setdefault(name,set()).add(sid); current["bound"].add(name)
        scope(sid,parent)
        return symbol
    def identifiers(node):
        if node is None:return []
        if node.type in {"identifier","shorthand_property_identifier_pattern"}:return [text(node)]
        if node.type in {"assignment_pattern","required_parameter","optional_parameter"}:
            return identifiers(field(node,"left") or field(node,"pattern") or field(node,"name") or (node.named_children[0] if node.named_children else None))
        if node.type=="pair_pattern":return identifiers(field(node,"value"))
        return [name for child in node.named_children for name in identifiers(child) if child.type not in {"type_annotation","type_identifier","property_identifier"}]
    def literal(node):
        value=text(node)
        if node is not None and node.type in {"string","interpreted_string_literal","raw_string_literal"} and len(value)>1:
            return value[1:-1]
        return None
    def callable_name(node):
        if node is None:return ""
        if node.type in {"identifier","property_identifier","this","super"}:return text(node)
        if node.type in {"member_expression","nested_identifier"}:
            a=callable_name(field(node,"object")); b=callable_name(field(node,"property"))
            return a+"."+b if a and b else ""
        if node.type=="call_expression":return callable_name(field(node,"function"))
        return ""
    def bind_import(owner,alias,spec,name):
        current=scope(owner,None); current["bound"].add(alias); current["bindings"].setdefault(alias,[]).append((spec,name))
        unit.imports.append(spec)
    def import_statement(node,owner):
        spec=literal(field(node,"source"))
        if spec is None:return
        unit.imports.append(spec)
        if re.match(r"import\s+type\b",text(node)):return
        for child in node.named_children:
            if child.type!="import_clause":continue
            for part in child.named_children:
                if part.type=="identifier":bind_import(owner,text(part),spec,"default")
                elif part.type=="namespace_import":bind_import(owner,text(part.named_children[-1]),spec,"*")
                elif part.type=="named_imports":
                    for item in part.named_children:
                        if re.match(r"type\s",text(item)):continue
                        original=field(item,"name"); alias=field(item,"alias") or original
                        if original is not None:bind_import(owner,text(alias),spec,text(original))
    def test_registration(node,owner):
        name=callable_name(field(node,"function")); base=name.split(".")[0]
        if not name:return False
        current=owner
        while current:
            info=unit.scopes[current]
            if base in info["bindings"]:
                return any(spec in {"vitest","@jest/globals","node:test"} and (target in {"test","it","default"} or target=="__require__" and spec=="node:test" or target=="*" and len(name.split("."))>1 and name.split(".")[1] in {"test","it"}) for spec,target in info["bindings"][base])
            if base in info["bound"]:return False
            current=info["parent"]
        test_path=bool(re.search(r"(?:^|/)(?:__tests__|tests?|test-[^/]+)(?:/|\.)|\.(?:test|spec)\.",path))
        return test_path and base in {"test","it"} and (not name.endswith(".each") or field(node,"function").type=="call_expression")
    def visit(node,owner,lexical,callback=False):
        kind=node.type
        if kind=="import_statement":import_statement(node,lexical);return
        if kind=="export_statement":
            declaration=field(node,"declaration"); spec=literal(field(node,"source"))
            if spec:unit.imports.append(spec)
            before=len(unit.symbols)
            if declaration is not None:
                visit(declaration,owner,lexical,callback)
                for symbol in unit.symbols[before:]:
                    if unit.scopes[symbol.id]["parent"]==unit.module:
                        unit.exports.setdefault("default" if re.match(r"export\s+default\b",text(node)) else symbol.name,[]).append(("local",symbol.name))
            else:
                for child in node.named_children:
                    if child.type=="export_clause":
                        for item in child.named_children:
                            name=field(item,"name"); alias=field(item,"alias") or name
                            if name is not None:unit.exports.setdefault(text(alias),[]).append((spec or "local",text(name)))
                if spec and "*" in text(node):unit.stars.append(spec);unit.imports.append(spec)
                value=field(node,"value")
                if value is not None and value.type=="identifier":unit.exports.setdefault("default",[]).append(("local",text(value)))
                elif value is not None and value.type in {"arrow_function","function_expression"}:
                    symbol=add(value,"default", "function",lexical); unit.exports.setdefault("default",[]).append(("local",symbol.name)); function_body(value,symbol,lexical)
            return
        if kind in {"function_declaration","generator_function_declaration"}:
            name=text(field(node,"name"))
            if not name:return
            symbol=add(node,name,"function",lexical); function_body(node,symbol,lexical);return
        if kind in {"class_declaration","abstract_class_declaration","interface_declaration","type_alias_declaration","enum_declaration"}:
            name=text(field(node,"name"))
            if not name:return
            symbol=add(node,name,"class",lexical)
            body=field(node,"body")
            if lexical==unit.module and body is not None:stripped_bodies.append((body.start_byte,body.end_byte))
            if body is not None:
                for child in body.named_children:visit(child,symbol.id,symbol.id,callback)
            return
        if kind in {"method_definition","method_signature","abstract_method_signature"}:
            name=text(field(node,"name"))
            if name:
                symbol=add(node,name,"function",lexical); function_body(node,symbol,lexical)
            return
        if kind=="variable_declarator":
            name=field(node,"name"); value=field(node,"value"); names=identifiers(name)
            scope(lexical,None)["bound"].update(names)
            if value is not None and value.type in {"arrow_function","function_expression","generator_function"} and name.type=="identifier":
                symbol=add(node,text(name),"function",lexical); function_body(value,symbol,lexical);return
            if value is not None and value.type=="call_expression" and text(field(value,"function"))=="require":
                args=field(value,"arguments"); spec=literal(args.named_children[0]) if args and args.named_children else None
                if spec is not None:
                    if name.type=="identifier":bind_import(lexical,text(name),spec,"__require__")
                    elif name.type=="object_pattern":
                        for item in name.named_children:
                            if item.type=="shorthand_property_identifier_pattern":bind_import(lexical,text(item),spec,text(item))
                            elif item.type=="pair_pattern":bind_import(lexical,text(field(item,"value")),spec,text(field(item,"key")))
                    return
            if value is not None:visit(value,owner,lexical,callback)
            return
        if kind in {"assignment_expression","augmented_assignment_expression","update_expression"}:
            left=field(node,"left") or field(node,"argument")
            if left is not None and left.type=="identifier":unit.scopes[lexical]["reassigned"].add(text(left))
            expression=callable_name(left)
            right=field(node,"right")
            if expression.startswith("exports.") or expression.startswith("module.exports."):
                if right is not None and right.type=="identifier":unit.exports.setdefault(expression.split(".")[-1],[]).append(("local",text(right)))
            elif expression=="module.exports" and right is not None:
                if right.type=="identifier":unit.exports.setdefault("default",[]).append(("local",text(right)))
                elif right.type=="object":
                    for item in right.named_children:
                        if item.type=="shorthand_property_identifier":unit.exports.setdefault(text(item),[]).append(("local",text(item)))
                        elif item.type=="pair" and field(item,"value").type=="identifier":unit.exports.setdefault(text(field(item,"key")),[]).append(("local",text(field(item,"value"))))
            if right is not None:visit(right,owner,lexical,callback)
            return
        if kind=="call_expression":
            args=field(node,"arguments"); children=args.named_children if args else []
            if test_registration(node,lexical) and len(children)>=2 and literal(children[0]) is not None:
                label=literal(children[0]); symbol=add(node,f"test[{label}]@{node.start_point.row+1}","function",lexical,True)
                value=children[-1]
                if value.type in {"arrow_function","function_expression"}:
                    body=field(value,"body")
                    if lexical==unit.module and body is not None:stripped_bodies.append((body.start_byte,body.end_byte))
                    function_body(value,symbol,lexical,strip=False)
                elif value.type=="identifier":unit.calls.append((symbol.id,text(value),value.start_point.row+1,symbol.id,"test_callback"))
                return
            expression=callable_name(field(node,"function")) or text(field(node,"function"))
            unit.calls.append((owner,expression,node.start_point.row+1,lexical,"callback_reference" if callback else "static_reference"))
        elif kind=="new_expression":
            unit.calls.append((owner,callable_name(field(node,"constructor")),node.start_point.row+1,lexical,"static_reference"))
        elif kind in {"jsx_opening_element","jsx_self_closing_element"}:
            expression=text(field(node,"name"))
            if expression and (expression[0].isupper() or "." in expression):unit.calls.append((owner,expression,node.start_point.row+1,lexical,"jsx_reference"))
        if kind in {"arrow_function","function_expression"}:
            anonymous=f"{lexical}.$callback@{node.start_byte}"; scope(anonymous,lexical)["bound"].update(identifiers(field(node,"parameters") or field(node,"parameter")))
            body=field(node,"body")
            if body is not None:visit(body,owner,anonymous,True)
            return
        for child in node.named_children:visit(child,owner,lexical,callback)
    def function_body(node,symbol,parent,strip=True):
        current=scope(symbol.id,parent); current["bound"].update(identifiers(field(node,"parameters") or field(node,"parameter")))
        body=field(node,"body")
        if strip and parent==unit.module and body is not None:stripped_bodies.append((body.start_byte,body.end_byte))
        if body is not None:visit(body,symbol.id,symbol.id)
    if language in {"javascript","typescript","tsx"}:
        visit(tree.root_node,unit.module,unit.module)
        key=raw
        for start,end in sorted(set(stripped_bodies),reverse=True):key=key[:start]+b"{}"+key[end:]
        module_symbol.change_key="module:"+key.decode("utf-8")
    elif language=='dart':
        from .dart_adapter import extract
        extract(unit,tree.root_node,text,field,add,scope)
        module_symbol.change_key='module:'+source
    else:
        structural(unit,tree.root_node,text,field,add,scope)
        module_symbol.change_key="module:"+source
        unit.warnings.append(f"{path}: {language} structural analysis only; symbol calls, runtime wiring, refactoring and test execution are not resolved.")
    return unit


def structural(unit,root,text,field,add,scope):
    """Declarations and explicit imports only; no guessed receiver/type resolution."""
    type_nodes={"class_declaration","interface_declaration","record_declaration","struct_item","enum_item","trait_item","enum_declaration","type_spec"}
    functions={"method_declaration","constructor_declaration","function_declaration","function_item","function_signature_item"}
    def walk(node,owner):
        if node.type in {"package_declaration","package_clause","namespace_declaration","file_scoped_namespace_declaration"}:
            name=field(node,"name") or next((n for n in node.named_children if n.type in {"identifier","scoped_identifier","package_identifier","qualified_name"}),None)
            if name is not None:unit.namespace=text(name)
        if node.type in {"import_declaration","using_directive","use_declaration"}:
            if unit.language=="go":
                pending=[node]
                while pending:
                    current=pending.pop()
                    if current.type=="import_spec":unit.imports.append(text(field(current,"path")).strip('"`'))
                    pending.extend(current.named_children)
            else:
                value=re.sub(r"^(?:import|using|use)\s+(?:static\s+)?","",text(node)).strip().rstrip(";")
                unit.imports.append(value)
        if unit.language=="rust" and node.type=="mod_item" and field(node,"body") is None:
            unit.imports.append("mod:"+text(field(node,"name")))
        if node.type in type_nodes:
            name=text(field(node,"name"))
            if name:
                symbol=add(node,name,"class",owner); owner=symbol.id
        elif node.type=="impl_item":
            name=text(field(node,"type"))
            owner=unit.path+":"+name;scope(owner,unit.module)
        elif node.type in functions:
            name=text(field(node,"name"))
            if name:
                attrs=" ".join(text(child) for child in node.named_children if child.type in {"attribute_list","modifiers"})
                previous=node.prev_named_sibling
                if previous is not None and previous.type=="attribute_item":attrs+=" "+text(previous)
                is_test=bool(re.search(r"\b(?:Test|Fact|Theory|TestMethod|ParameterizedTest|test)\b",attrs))
                if unit.language=="go":is_test=unit.path.endswith("_test.go") and (name.startswith("Test") and (len(name)==4 or not name[4].islower()) or name.startswith("Example"))
                symbol=add(node,name,"function",owner,is_test)
                return
        for child in node.named_children:walk(child,owner)
    walk(root,unit.module)
