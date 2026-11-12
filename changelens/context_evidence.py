"""Read bounded definitions from the saved source index for focused model requests."""

import ast
import hashlib
from pathlib import Path
import re

from .core import decode_source, module_name
from .languages import TYPESCRIPT_LANGUAGES, language_for


_SCAN_BYTES = 64 * 1024
_MODULE_LINKS = {"module_import", "structural_import", "package_scope"}
_VARIABLES = {"variable_declarator", "const_spec", "var_spec", "const_item", "static_item",
              "static_final_declaration", "initialized_identifier"}
_BODY_NODES = {"block", "statement_block", "function_body", "arrow_function", "function_expression"}
_STATEMENTS = {"lexical_declaration", "variable_declaration", "field_declaration", "const_declaration"}


def saved_source(snapshot, path):
    module = snapshot.symbols.get(f"{path}:<module>")
    if module is not None:
        return module.source if len(module.source.encode("utf-8")) <= _SCAN_BYTES else None
    # Python's index stores declarations without a full-file symbol.
    digest = snapshot.hashes.get(path)
    if not digest or digest in {"oversized", "unreadable"}:
        return None
    root = Path(snapshot.root).resolve()
    target = root / path
    try:
        if target.is_symlink() or not target.resolve().is_relative_to(root):
            return None
        with target.open("rb") as stream:
            raw = stream.read(_SCAN_BYTES + 1)
        if len(raw) <= _SCAN_BYTES and hashlib.sha256(raw).hexdigest() == digest:
            return decode_source(raw, path)
    except (OSError, UnicodeError, LookupError, ValueError):
        return None
    return None


def _python_imports(snapshot, symbol, source, names):
    """Match explicit imports in the file or selected definition to unique local modules."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    package = module_name(symbol.path).split(".")
    if Path(symbol.path).name != "__init__.py":
        package = package[:-1]
    available = {}
    for path in snapshot.hashes:
        if language_for(path) == "python" and path != symbol.path:
            available.setdefault(module_name(path), []).append(path)
    links = {}
    imports = (node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
               and (node in tree.body or symbol.start <= node.lineno <= symbol.end))
    for node in imports:
        if isinstance(node, ast.ImportFrom):
            if node.level > len(package) + 1:
                continue
            prefix = package[:len(package) - node.level + 1] if node.level else []
            module = ".".join(prefix + ([node.module] if node.module else []))
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            if local not in names:
                continue
            if isinstance(node, ast.Import):
                candidates = [(alias.name, names)]
            else:
                submodule = ".".join(filter(None, [module, alias.name]))
                candidates = [(submodule, names), (module, {alias.name})]
            for requested, wanted in candidates:
                paths = available.get(requested, ())
                if len(paths) == 1:
                    _, matched = links.setdefault(paths[0], ("local Python import", set()))
                    matched.update(wanted)
                    break
                if len(paths) > 1:
                    break
    return links


def context_files(snapshot, symbol, names, edges):
    """Reuse the existing module links and expand named JavaScript/TypeScript aliases."""
    language = language_for(symbol.path)
    source = saved_source(snapshot, symbol.path)
    if language == "python" and source:
        return _python_imports(snapshot, symbol, source, names)
    module_id = f"{symbol.path}:<module>"
    imports = [edge for edge in edges if edge["caller"] == module_id and edge["kind"] in _MODULE_LINKS]
    package_peers = {edge["callee"] for edge in imports if edge["kind"] == "package_scope"}
    if package_peers:
        # The index uses a hub for a package. Follow that hub once to reach peer files.
        imports.extend(edge for edge in edges if edge["caller"] in package_peers and edge["kind"] == "package_scope")
    aliases = {}
    if imports and language in TYPESCRIPT_LANGUAGES and source:
        from .syntax import parse_unit
        try:
            unit = parse_unit(symbol.path, source)
        except (SyntaxError, ValueError, RecursionError):
            unit = None
        if unit:
            for scope_id in (module_id, symbol.id):
                for local, bindings in unit.scopes.get(scope_id, {}).get("bindings", {}).items():
                    if local in names and len(set(bindings)) == 1:
                        spec, exported = bindings[0]
                        if exported.isidentifier():
                            aliases.setdefault(spec, set()).add(exported)
    links = {}
    imports.sort(key=lambda edge: (edge["kind"] == "package_scope", edge["callee"], edge["line"]))
    for edge in imports:
        target = snapshot.symbols.get(edge["callee"])
        if target is None or target.path == symbol.path:
            continue
        expression = edge.get("expression", "")
        alias_names = aliases.get(expression.removeprefix("imports "), set())
        _, matched = links.setdefault(target.path, (expression or edge["kind"], set()))
        matched.update(names | alias_names)
    if language == "java":
        # Default-package Java files have no package edge. A qualified use and
        # unique class in the same directory are useful evidence, not type resolution.
        qualifiers = set(re.findall(r"\b([A-Za-z_$][\w$]*)\s*\.", symbol.source))
        candidates = {}
        for item in snapshot.symbols.values():
            if (item.path != symbol.path and item.path.endswith(".java") and item.name in qualifiers
                    and item.kind == "class" and Path(item.path).parent == Path(symbol.path).parent):
                candidates.setdefault(item.name, set()).add(item.path)
        for paths in candidates.values():
            if len(paths) == 1:
                links.setdefault(next(iter(paths)), ("same-folder Java type candidate", set(names)))
    return links


def definition_fragments(path, source, names):
    """Yield declarations of matching data names, skipping comments and function bodies."""
    if language_for(path) == "python":
        try:
            pending = list(reversed(ast.parse(source).body))
        except SyntaxError:
            return
        while pending:
            node = pending.pop()
            if isinstance(node, ast.ClassDef):
                pending.extend(reversed(node.body))
            targets = (node.targets if isinstance(node, ast.Assign) else
                       [node.target] if isinstance(node, ast.AnnAssign) and node.value is not None else [])
            if any(isinstance(target, ast.Name) and target.id in names for target in targets):
                yield node.lineno, node.end_lineno, ast.get_source_segment(source, node)
        return

    from .syntax import source_tree
    raw = source.encode("utf-8")
    root = source_tree(path, raw).root_node
    if root.has_error:
        return
    pending = [root]
    while pending:
        node = pending.pop()
        if node.type in _BODY_NODES:
            continue
        pending.extend(reversed(node.named_children))
        if node.type not in _VARIABLES:
            continue
        name = node.child_by_field_name("name")
        if name is None and node.type in {"static_final_declaration", "initialized_identifier"}:
            name = next((child for child in node.named_children if child.type == "identifier"), None)
        if name is None or raw[name.start_byte:name.end_byte].decode("utf-8") not in names:
            continue
        statement = node
        while statement.parent is not None and statement.parent.type in _STATEMENTS:
            statement = statement.parent
        yield statement.start_point.row + 1, statement.end_point.row + 1, raw[statement.start_byte:statement.end_byte].decode("utf-8")
