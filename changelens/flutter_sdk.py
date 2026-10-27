"""Use an existing SDK explicitly; never bootstrap Flutter or install packages."""
import os
from pathlib import Path
from .core import app_dir


def detect_sdk(interpreter=''):
    candidates=[]
    if interpreter and Path(interpreter).suffix.lower()=='.exe' and Path(interpreter).stem.lower()=='dart':candidates.append(Path(interpreter))
    if os.environ.get('FLUTTER_ROOT'):candidates.append(Path(os.environ['FLUTTER_ROOT'])/'bin/cache/dart-sdk/bin/dart.exe')
    for value in os.environ.get('PATH','').split(os.pathsep):
        folder=Path(value.strip('"'))
        if not folder.is_absolute():continue
        if (folder/'dart.exe').is_file():candidates.append(folder/'dart.exe')
        if (folder/'flutter.bat').is_file() or (folder/'dart.bat').is_file():candidates.append(folder/'cache/dart-sdk/bin/dart.exe')
    for dart in candidates:
        if dart.is_file() and (dart.parent.parent/'lib/core/core.dart').is_file():
            dart=dart.resolve()
            # .../flutter/bin/cache/dart-sdk/bin/dart.exe
            flutter=dart.parents[4] if dart.parent.parent.parent.name=='cache' else None
            return {'dart':dart,'flutter':flutter}
    return None


def sdk_environment():
    settings=app_dir()/'sdk-settings';settings.mkdir(parents=True,exist_ok=True)
    return {'CI':'true','DART_SUPPRESS_ANALYTICS':'true','FLUTTER_SUPPRESS_ANALYTICS':'true','APPDATA':str(settings),
            'FLUTTER_STORAGE_BASE_URL':'http://127.0.0.1:9','PUB_HOSTED_URL':'http://127.0.0.1:9'}


def flutter_command(snapshot,symbols,interpreter=''):
    root=Path(snapshot.root);paths=sorted({snapshot.symbols[sid].path for sid in symbols})
    packages=set()
    for path in paths:
        candidates=[str(Path(name).parent.as_posix()) for name,data in snapshot.profile.get('manifests',{}).items() if Path(name).name in {'pubspec.yaml','pubspec.yml'} and data.get('flutter') and (str(Path(name).parent)=='.' or path.startswith(Path(name).parent.as_posix()+'/'))]
        if not candidates:raise ValueError('Flutter test execution requires a Flutter pubspec. Standalone Dart tests currently receive recommendations only.')
        packages.add(max(candidates,key=len))
    if len(packages)!=1:raise ValueError('Select Flutter tests from one package at a time.')
    cwd=(root/next(iter(packages))).resolve();sdk=detect_sdk(interpreter)
    if not sdk or not sdk['flutter']:raise ValueError('A prepared Flutter SDK is required. Add its bin folder to PATH or choose its cached dart.exe in Advanced run options.')
    flutter=sdk['flutter'];snapshot_path=flutter/'bin/cache/flutter_tools.snapshot';tool_config=flutter/'packages/flutter_tools/.dart_tool/package_config.json'
    required=[snapshot_path,tool_config,flutter/'bin/cache/artifacts/engine/windows-x64/flutter_tester.exe',cwd/'.dart_tool/package_config.json']
    if not all(path.is_file() for path in required):raise ValueError('Prepare the Flutter SDK cache and this project’s dependencies outside Change Lens first. No SDK or pub downloads are started by the app.')
    command=[str(sdk['dart']),'--packages='+str(tool_config),str(snapshot_path),'--suppress-analytics','--no-version-check','test','--no-pub','--reporter','expanded',*[str((root/path).resolve()) for path in paths]]
    return command,cwd,'Flutter selected test files (all tests in those files may run; pub resolution disabled)',len(paths)
