"""Resolve lexical bindings using Python's symbol tables, without importing code."""
import ast
import symtable


class ScopedCalls:
    def __init__(self, symbols, imports, sources, resolve, absolute_import, module_name):
        self.symbols, self.imports = symbols, imports
        self.resolve, self.absolute_import, self.module_name = resolve, absolute_import, module_name
        self.tables = {}
        self.modules = {}
        self.writes = {}
        for path, source in sources.items():
            try:
                table = symtable.symtable(source, path, "exec")
            except SyntaxError:
                continue
            self.modules[path] = table
            writes = self.writes

            class Writes(ast.NodeVisitor):
                scope = ""

                def visit_Name(self, node):
                    if isinstance(node.ctx, (ast.Store, ast.Del)):
                        writes.setdefault((path, self.scope), set()).add(node.id)

                def visit_FunctionDef(self, node):
                    previous = self.scope
                    self.scope = ".".join(filter(None, [previous, node.name]))
                    for statement in node.body:
                        self.visit(statement)
                    self.scope = previous

                visit_AsyncFunctionDef = visit_FunctionDef
                visit_ClassDef = visit_FunctionDef

                def visit_Lambda(self, node):
                    pass

                visit_ListComp = visit_Lambda
                visit_SetComp = visit_Lambda
                visit_DictComp = visit_Lambda
                visit_GeneratorExp = visit_Lambda

            Writes().visit(ast.parse(source))

            def visit(parent, prefix=""):
                for child in parent.get_children():
                    name = ".".join(filter(None, [prefix, child.get_name()]))
                    sid = f"{path}:{name}"
                    symbol = symbols.get(sid)
                    if symbol and symbol.start <= child.get_lineno() <= symbol.end:
                        self.tables[sid] = child
                        visit(child, name)
            visit(table)

    def candidates(self, caller, expression):
        parts = expression.split(".")
        if not all(part.isidentifier() for part in parts):
            return []
        first, *tail = parts
        symbol = self.symbols[caller]
        scope = symbol
        while scope:
            table = self.tables.get(scope.id)
            try:
                binding = table.lookup(first) if table else None
            except KeyError:
                binding = None
            if binding and binding.is_global():
                if binding.is_assigned() or binding.is_imported():
                    return []
                break
            if binding and binding.is_nonlocal() and binding.is_assigned():
                return []
            if binding and binding.is_local():
                return self.bound(scope.path, scope.id, scope.qualname, binding, expression, tail)
            # A method's unqualified names do not capture its class namespace.
            parent = scope.qualname.rsplit(".", 1)[0] if "." in scope.qualname else ""
            scope = self.symbols.get(f"{symbol.path}:{parent}")
            while scope and scope.kind == "class":
                parent = scope.qualname.rsplit(".", 1)[0] if "." in scope.qualname else ""
                scope = self.symbols.get(f"{symbol.path}:{parent}")
        table = self.modules.get(symbol.path)
        try:
            binding = table.lookup(first) if table else None
        except KeyError:
            binding = None
        return self.bound(symbol.path, None, "", binding, expression, tail) if binding else []

    def unmodified_receiver(self, caller, name):
        table = self.tables.get(caller)
        if not table:
            return False
        try:
            binding = table.lookup(name)
        except KeyError:
            return False
        symbol = self.symbols[caller]
        return binding.is_parameter() and name not in self.writes.get((symbol.path, symbol.qualname), set())

    def bound(self, path, owner, prefix, binding, expression, tail):
        if binding.get_name() in self.writes.get((path, prefix), set()):
            return []
        if binding.is_imported() and not binding.is_assigned():
            targets = {self.absolute_import(path, target, level)
                       for binding_owner, alias, target, level in self.imports.get(path, [])
                       if binding_owner == owner and alias == binding.get_name()}
            # Conditional imports with multiple meanings stay unresolved.
            if len(targets) != 1:
                return []
            return self.resolve(".".join([next(iter(targets))] + tail))
        if binding.is_namespace() and not binding.is_imported() and not binding.is_parameter():
            if len(binding.get_namespaces()) != 1:
                return []
            name = ".".join(filter(None, [self.module_name(path), prefix, expression]))
            return self.resolve(name)
        return []
