"""Static Python completion. No LLM, remote API or target-source execution."""
from pathlib import Path


def complete_python(code: str, path: str, line: int, column: int, root: str):
    import jedi
    from jedi.api.environment import InterpreterEnvironment
    jedi.settings.auto_import_modules = []
    project = jedi.Project(path=root, load_unsafe_extensions=False)
    script = jedi.Script(code=code, path=path, project=project, environment=InterpreterEnvironment())
    return [{"name": item.name, "type": item.type, "description": item.description}
            for item in script.complete(line=line, column=column)][:80]


def find_definition(code: str, path: str, line: int, column: int, root: str):
    import jedi
    from jedi.api.environment import InterpreterEnvironment
    project = jedi.Project(path=root, load_unsafe_extensions=False)
    script = jedi.Script(code=code, path=path, project=project, environment=InterpreterEnvironment())
    return [{"path": str(item.module_path), "line": item.line, "name": item.name}
            for item in script.goto(line=line, column=column, follow_imports=True) if item.module_path and item.line]
