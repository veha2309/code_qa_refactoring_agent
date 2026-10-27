"""Static pytest dependencies; no collection, imports or plugin execution."""
import ast
from pathlib import Path


def fixture_edges(symbols, nodes, imports, sources, resolve, absolute_import, checkpoint, cancel, class_nodes=None):
    fixtures, automatic, warnings = {}, set(), []

    def canonical(path, expression):
        parts = expression.split(".")
        bindings = {target for owner, alias, target, level in imports.get(path, [])
                    if owner is None and level == 0 and alias == parts[0]}
        if len(bindings) == 1:
            return ".".join([next(iter(bindings))] + parts[1:])
        return ""

    def decorators(path, node, target):
        for decorator in node.decorator_list:
            call = decorator.func if isinstance(decorator, ast.Call) else decorator
            if canonical(path, ast.unparse(call)) == target:
                yield decorator

    for sid, node in nodes.items():
        checkpoint(cancel)
        symbol = symbols[sid]
        if "." in symbol.qualname:
            parent = symbols.get(f"{symbol.path}:{symbol.qualname.rsplit('.', 1)[0]}")
            if not parent or parent.kind != "class":
                continue
        for decorator in decorators(symbol.path, node, "pytest.fixture"):
            name = node.name
            if isinstance(decorator, ast.Call):
                for option in decorator.keywords:
                    if option.arg == "name" and isinstance(option.value, ast.Constant) and isinstance(option.value.value, str):
                        name = option.value.value
                    if option.arg == "autouse":
                        if isinstance(option.value, ast.Constant) and option.value.value is True:
                            automatic.add(sid)
                        elif not isinstance(option.value, ast.Constant):
                            warnings.append(f"Dynamic autouse setting on {sid}: automatic fixture links may be missing.")
            fixtures.setdefault(name, []).append(sid)
    fixture_ids = {sid for group in fixtures.values() for sid in group}

    def parent_class(symbol):
        name = symbol.qualname.rsplit(".", 1)[0] if "." in symbol.qualname else ""
        parent = symbols.get(f"{symbol.path}:{name}")
        return name if parent and parent.kind == "class" else ""

    def locations(symbol):
        result = [(symbol.path, parent_class(symbol)), (symbol.path, "")]
        directory = Path(symbol.path).parent
        while True:
            result.append(((directory / "conftest.py").as_posix(), ""))
            if directory == Path("."):
                return list(dict.fromkeys(result))
            directory = directory.parent

    def find(symbol, name):
        candidates = fixtures.get(name, [])
        for path, scope in locations(symbol):
            matches = [sid for sid in candidates if symbols[sid].path == path and parent_class(symbols[sid]) == scope]
            if matches:
                # A fixture requesting its own name asks for the overridden parent.
                matches = [sid for sid in matches if sid != symbol.id]
                if matches:
                    return matches[0] if len(matches) == 1 else None
        imported = set()
        for owner, alias, target, level in imports.get(symbol.path, []):
            if owner is None and alias == name:
                imported.update(sid for sid in resolve(absolute_import(symbol.path, target, level)) if sid in fixture_ids)
        return next(iter(imported)) if len(imported) == 1 else None

    module_marks, class_marks = {}, {}

    def marked_names(path, values):
        names = set()
        for value in values:
            if isinstance(value, (ast.List, ast.Tuple)):
                names.update(marked_names(path, value.elts))
            elif isinstance(value, ast.Call) and canonical(path, ast.unparse(value.func)) == "pytest.mark.usefixtures":
                for argument in value.args:
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                        names.add(argument.value)
                    else:
                        warnings.append(f"Dynamic usefixtures marker in {path}:{value.lineno}: fixture name unresolved.")
        return names

    for path, source in sources.items():
        checkpoint(cancel)
        tree = ast.parse(source,filename=path)
        values = [node.value for node in tree.body if isinstance(node, (ast.Assign, ast.AnnAssign))
                  and any(isinstance(target, ast.Name) and target.id == "pytestmark"
                          for target in (node.targets if isinstance(node, ast.Assign) else [node.target]))]
        module_marks[path] = marked_names(path, values)
    for sid, symbol in symbols.items():
        if symbol.kind == "class":
            from .python_source import symbol_node
            node=(class_nodes or {}).get(sid)
            if node is None:node=symbol_node(symbol)
            class_marks[sid] = marked_names(symbol.path, node.decorator_list)

    edges = []
    for sid, node in nodes.items():
        checkpoint(cancel)
        symbol = symbols[sid]
        if not symbol.is_test and sid not in fixture_ids:
            continue
        parameters = {arg.arg for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs} - {"self", "cls"}
        direct = set()
        for decorator in decorators(symbol.path, node, "pytest.mark.parametrize"):
            if not isinstance(decorator, ast.Call) or not decorator.args:
                continue
            argument = decorator.args[0]
            names = set()
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                names = {name.strip() for name in argument.value.split(",")}
            elif isinstance(argument, (ast.Tuple, ast.List)):
                names = {item.value for item in argument.elts if isinstance(item, ast.Constant) and isinstance(item.value, str)}
            indirect = set()
            for option in decorator.keywords:
                if option.arg == "indirect":
                    if isinstance(option.value, ast.Constant) and option.value.value is True:
                        indirect = names
                    elif isinstance(option.value, (ast.Tuple, ast.List)):
                        indirect = {item.value for item in option.value.elts if isinstance(item, ast.Constant)}
                    elif not isinstance(option.value, ast.Constant):
                        warnings.append(f"Dynamic indirect parametrization in {sid}: fixture links may be incomplete.")
            direct.update(names - indirect)
        requested = {name: "parameter" for name in parameters - direct}
        if symbol.is_test:
            marks = module_marks.get(symbol.path, set()) | class_marks.get(f"{symbol.path}:{parent_class(symbol)}", set())
            marks |= marked_names(symbol.path, node.decorator_list)
            for name in marks - direct:
                requested[name] = "usefixtures"
            visible = set(locations(symbol))
            for name, group in fixtures.items():
                if name not in direct and any(fid in automatic and (symbols[fid].path, parent_class(symbols[fid])) in visible for fid in group):
                    requested.setdefault(name, "autouse")
        for name, via in requested.items():
            target = find(symbol, name)
            if target:
                edges.append({"caller": sid, "callee": target, "line": symbol.start,
                              "expression": f"pytest fixture {name} ({via})", "kind": "fixture_dependency", "via": via})
            elif name not in {"request"}:
                warnings.append(f"Unresolved pytest fixture {name} requested by {sid} ({via}); it may come from a plugin or dynamic setup.")
    return edges, warnings
