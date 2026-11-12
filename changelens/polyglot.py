"""Conservative module and lexical reference linking for syntax adapters."""
from pathlib import PurePosixPath
import posixpath
import re

from .languages import language_for

JS={"javascript","typescript","tsx"}
INFERRED_KINDS={"inferred_method","enclosing_scope","historical_reference","callback_reference","test_callback","module_scope","package_scope","structural_import"}
INFERRED_KINDS.add('flutter_build')


def link_units(root,units,profile,cancel=None):
    from .core import checkpoint
    edges=[]; warnings=[]; all_symbols={s.id:s for unit in units.values() for s in unit.symbols}
    class_ids={sid for sid,s in all_symbols.items() if s.kind=="class"}
    def normalize(path):return posixpath.normpath(path).replace("\\","/")
    def candidate(base,requester):
        base=normalize(base)
        if base.startswith(("../","/")) or base=="..":return None
        choices=[]
        if base in units:choices=[base]
        elif requester.language in JS:
            suffix=PurePosixPath(base).suffix
            bases=[base]
            if suffix in {".js",".jsx",".mjs",".cjs"}:bases=[base[:-len(suffix)]]
            extensions=(".ts",".tsx",".mts",".cts") if suffix else (".js",".jsx",".mjs",".cjs",".ts",".tsx",".mts",".cts")
            choices=[value+ext for value in bases for ext in extensions if value+ext in units]
            if not suffix:choices += [base+"/index"+ext for ext in extensions if base+"/index"+ext in units]
        if len(set(choices))==1:return choices[0]
        if len(set(choices))>1:warnings.append(f"Ambiguous module target in {requester.path}: {base}; no target was chosen.")
        return None
    def resolve_spec(unit,spec):
        if spec.startswith("."):return candidate(posixpath.join(posixpath.dirname(unit.path),spec),unit)
        configs=[(path,data) for path,data in profile.get("manifests",{}).items() if PurePosixPath(path).name in {"tsconfig.json","jsconfig.json"}
                 and (posixpath.dirname(path)=="" or unit.path.startswith(posixpath.dirname(path)+"/"))]
        for path,data in sorted(configs,key=lambda item:len(item[0]),reverse=True)[:1]:
            options=data.get("compilerOptions",{})
            if not isinstance(options,dict):continue
            base=posixpath.join(posixpath.dirname(path),str(options.get("baseUrl",".")))
            aliases=options.get("paths",{})
            if isinstance(aliases,dict):
                found=set()
                for pattern,targets in aliases.items():
                    if not isinstance(targets,list):continue
                    regex="^"+re.escape(pattern).replace(r"\*","(.*)")+"$"; match=re.match(regex,spec)
                    if not match:continue
                    for target in targets:
                        if not isinstance(target,str):continue
                        target=target.replace("*",match.group(1) if match.groups() else "")
                        resolved=candidate(posixpath.join(base,target),unit)
                        if resolved:found.add(resolved)
                if len(found)==1:return next(iter(found))
                if len(found)>1:warnings.append(f"Ambiguous configuration alias {spec} in {unit.path}");return None
            if "baseUrl" in options:
                resolved=candidate(posixpath.join(base,spec),unit)
                if resolved:return resolved
        return None
    def exported(path,name,visited=None):
        visited=set() if visited is None else visited
        key=(path,name)
        if key in visited or len(visited)>64:return set()
        visited=visited|{key}; unit=units[path]; targets=set()
        definitions=unit.exports.get(name,[])
        if len(definitions)>1:return set()
        for spec,target in definitions:
            if spec=="local":targets.update(lookup(unit,unit.module,target,visited))
            else:
                resolved=resolve_spec(unit,spec)
                if resolved:targets.update(exported(resolved,target,visited))
        if not definitions and name!="default":
            for spec in unit.stars:
                resolved=resolve_spec(unit,spec)
                if resolved:targets.update(exported(resolved,name,visited))
        return targets
    def members(ids,tail):
        for part in tail:
            ids={sid+"."+part for sid in ids if sid in class_ids and sid+"."+part in all_symbols}
        return ids
    def lookup(unit,start,expression,visited=None):
        parts=expression.split(".")
        if not all(part.isidentifier() for part in parts):return set()
        first,*tail=parts; current=start
        while current:
            checkpoint(cancel); info=unit.scopes.get(current)
            if info is None:break
            if first in info["reassigned"]:return set()
            if current in class_ids and current!=start:
                current=info["parent"];continue
            if first in info["defs"]:return members(set(info["defs"][first]),tail)
            if first in info["bindings"]:
                bindings=set(info["bindings"][first])
                if len(bindings)!=1:return set()
                spec,name=next(iter(bindings)); target=resolve_spec(unit,spec)
                if not target:return set()
                if name in {"*","__require__"}:
                    if tail:return members(exported(target,tail[0],visited),tail[1:])
                    return exported(target,"default",visited) if name=="__require__" else set()
                return members(exported(target,name,visited),tail)
            if first in info["bound"]:return set()
            current=info["parent"]
        return set()
    def edge(caller,callee,line,expression,kind):
        if caller in all_symbols and callee in all_symbols:
            edges.append({"caller":caller,"callee":callee,"line":line,"expression":expression,"kind":kind})
    for path,unit in units.items():
        checkpoint(cancel); warnings.extend(unit.warnings)
        for symbol in unit.symbols:
            if symbol.id!=unit.module:edge(symbol.id,unit.module,symbol.start,"depends on file/module setup","module_scope")
        if unit.language not in JS:continue
        for spec in sorted(set(unit.imports)):
            target=resolve_spec(unit,spec)
            if target:
                for line in sorted(set(unit.import_lines.get(spec,[1]))):edge(unit.module,units[target].module,line,"imports "+spec,"module_import")
            elif spec.startswith(".") or spec.startswith(("@/","~/")):
                line=unit.import_lines.get(spec,[1])[0];warnings.append(f"Unresolved local module {spec} imported by {path}:{line}")
        for caller,expression,line,lexical,kind in unit.calls:
            checkpoint(cancel); matches=set()
            if expression.startswith("this."):
                parent=unit.scopes.get(lexical,{}).get("parent")
                while parent and parent not in class_ids:parent=unit.scopes.get(parent,{}).get("parent")
                target=(parent or "")+"."+expression.split(".",1)[1]
                if target in all_symbols:matches.add(target);kind="inferred_method"
            else:matches=lookup(unit,lexical,expression)
            if len(matches)==1:edge(caller,next(iter(matches)),line,expression,kind)
            elif expression and expression not in {"require","describe","expect","test","it"}:
                warnings.append(f"Unresolved call/reference {path}:{line}: {expression} (external, dynamic, shadowed or ambiguous)")
    # Structural adapters expose file/package relationships, not inferred method targets.
    go_modules=[]
    for path in profile.get("config_paths",[]):
        if PurePosixPath(path).name=="go.mod":
            try:
                text=(root/path).read_text(encoding="utf-8-sig"); match=re.search(r"(?m)^module\s+(\S+)",text)
                if match:go_modules.append((posixpath.dirname(path),match.group(1)))
            except (OSError,UnicodeError):pass
    for unit in units.values():
        if unit.language in JS:continue
        checkpoint(cancel)
        for spec in sorted(set(unit.imports)):
            targets=[]
            if unit.language in {"java","csharp"}:
                name=spec.split("=")[-1].strip(); namespace=name.rsplit(".",1)[0] if unit.language=="java" and not name.endswith(".*") else name.rstrip(".*")
                targets=[other for other in units.values() if other.language==unit.language and other.namespace and other.namespace in {name,namespace}]
            elif unit.language=="go":
                for directory,module in go_modules:
                    if spec==module or spec.startswith(module+"/"):
                        folder=normalize(posixpath.join(directory,spec[len(module):].lstrip("/")))
                        targets=[other for other in units.values() if other.language=="go" and normalize(posixpath.dirname(other.path))==folder and not other.path.endswith("_test.go")]
            elif unit.language=="rust":
                if spec.startswith("mod:"):
                    base=posixpath.join(posixpath.dirname(unit.path),spec[4:]); options=[base+".rs",base+"/mod.rs"]
                elif spec.startswith("crate::"):
                    base="src/"+spec[7:].split("::{")[0].replace("::","/"); options=[]
                    while base.startswith("src/"):
                        options.extend([base+".rs",base+"/mod.rs"]); base=posixpath.dirname(base)
                else:options=[]
                target=next((path for path in options if path in units),None)
                if target:targets=[units[target]]
            for target in targets:
                if target.path!=unit.path:edge(unit.module,target.module,1,"structural import "+spec,"structural_import")
    groups={}
    for unit in units.values():
        if unit.language=="go":groups.setdefault((unit.language,posixpath.dirname(unit.path),unit.namespace),[]).append(unit)
        elif unit.language in {"java","csharp"} and unit.namespace:groups.setdefault((unit.language,unit.namespace),[]).append(unit)
    for group in groups.values():
        group=sorted(group,key=lambda unit:unit.path); hub=group[0]
        for other in group[1:]:
            edge(hub.module,other.module,1,"shared package/namespace scope (conservative)","package_scope")
            edge(other.module,hub.module,1,"shared package/namespace scope (conservative)","package_scope")
    from .dart_adapter import link
    dart_edges,dart_warnings=link(root,units,profile,cancel);edges.extend(dart_edges);warnings.extend(dart_warnings)
    return edges,list(dict.fromkeys(warnings))


def historical_links(snapshot,old_sources,historical,cancel=None):
    """Resolve surviving source bindings against removed identities, labeled historical."""
    from pathlib import Path
    from .core import decode_source,checkpoint
    from .syntax import parse_unit
    units={}; root=Path(snapshot.root)
    for path,digest in snapshot.hashes.items():
        checkpoint(cancel)
        if language_for(path) is None or language_for(path)=="python" or digest in {"unreadable","oversized"}:continue
        try:units[path]=parse_unit(path,decode_source((root/path).read_bytes(),path))
        except (OSError,UnicodeError,SyntaxError):pass
    paths={value["path"] for value in historical.values() if language_for(value["path"])!="python"}
    for path in paths:
        try:old=parse_unit(path,old_sources.get(path,""))
        except (SyntaxError,ValueError):continue
        if path not in units:
            old.calls=[];units[path]=old;continue
        current=units[path]
        for symbol in old.symbols:
            if symbol.id not in historical:continue
            current.symbols.append(symbol)
            if symbol.id in old.scopes:current.scopes.setdefault(symbol.id,old.scopes[symbol.id])
            parent=old.scopes.get(symbol.id,{}).get("parent")
            if parent in current.scopes:current.scopes[parent]["defs"].setdefault(symbol.name,set()).add(symbol.id)
            for name,bindings in old.exports.items():
                if ("local",symbol.name) in bindings:current.exports.setdefault(name,bindings)
    linked,_=link_units(root,units,snapshot.profile,cancel)
    return [{**edge,"kind":"historical_reference"} for edge in linked if edge["callee"] in historical and edge["caller"] in snapshot.symbols]
