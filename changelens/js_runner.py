"""Select existing Node test tools without npm, installs, or script execution."""
from pathlib import Path
import shutil

from .languages import language_for


def execution_family(snapshot,symbols):
    if not snapshot or not symbols:return None
    if any(sid not in snapshot.symbols or not snapshot.symbols[sid].is_test for sid in symbols):return None
    languages={language_for(snapshot.symbols[sid].path) for sid in symbols if sid in snapshot.symbols}
    if languages=={"python"}:return "python"
    if languages=={'dart'}:return 'dart'
    if languages and languages<={"javascript","typescript","tsx"}:return "javascript"
    return None


def detect_node(root):
    for relative in ("node.exe",".node/node.exe",".node/bin/node"):
        path=Path(root)/relative
        if path.is_file():return str(path.resolve())
    return shutil.which("node") or ""


def javascript_command(snapshot,symbols,interpreter=""):
    from .syntax import parse_unit
    root=Path(snapshot.root); paths=sorted({snapshot.symbols[sid].path for sid in symbols})
    if not paths:raise ValueError("Choose discovered JavaScript/TypeScript tests first.")
    manifests=snapshot.profile.get("manifests",{})
    packages=set()
    for path in paths:
        candidates=[str(Path(name).parent.as_posix()) for name in manifests if Path(name).name=="package.json" and (str(Path(name).parent)=="." or path.startswith(Path(name).parent.as_posix()+"/"))]
        packages.add(max(candidates,key=len) if candidates else ".")
    if len(packages)>1:raise ValueError("Select tests from one JavaScript package at a time.")
    cwd=(root/next(iter(packages))).resolve()
    executable=str(Path(interpreter).resolve()) if interpreter and Path(interpreter).stem.lower().startswith("node") else detect_node(root)
    if not executable or not Path(executable).is_file():raise ValueError("Install Node.js or choose node.exe in Advanced run options. Recommendations remain available without Node.")
    imports=set()
    for path in paths:
        imports.update(parse_unit(path,(root/path).read_text(encoding="utf-8-sig")).imports)
    explicit=imports & {"node:test","vitest","@jest/globals"}
    if len(explicit)>1:raise ValueError("Select tests using one test runner at a time (Node, Jest or Vitest).")
    files=[str((root/path).resolve()) for path in paths]
    if "node:test" in imports and all(Path(path).suffix in {".js",".mjs",".cjs"} for path in paths):
        return [executable,"--test",*files],cwd,"Node.js selected test files (all tests inside those files may run)",len(files)
    folders=[]; folder=cwd
    while folder.is_relative_to(root):
        folders.append(folder)
        if folder==root:break
        folder=folder.parent
    options=[]
    for label,entry in (("Vitest","vitest/vitest.mjs"),("Jest","jest/bin/jest.js")):
        for folder in folders:
            target=folder/"node_modules"/entry
            if target.is_file():options.append((label,target));break
    if "vitest" in imports:options=[item for item in options if item[0]=="Vitest"]
    elif "@jest/globals" in imports:options=[item for item in options if item[0]=="Jest"]
    if len(options)>1:raise ValueError("Both Jest and Vitest are installed. Use explicit test imports so the runner can be selected unambiguously.")
    if not options:raise ValueError("No suitable installed test tool found. JS Node tests need node:test; TS/TSX or framework tests need this project's Jest/Vitest dependencies. The app does not install dependencies or run npm scripts.")
    label,target=options[0]
    if label=="Vitest":command=[executable,str(target),"run",*files]; scope="Vitest selected path filters (all tests in matching files may run)"
    else:command=[executable,str(target),"--runInBand","--runTestsByPath",*files];scope="Jest selected test files (all tests inside those files may run)"
    return command,cwd,scope,len(files)
