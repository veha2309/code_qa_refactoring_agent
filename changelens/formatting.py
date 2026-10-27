"""Isolated document formatting. Never loads project configuration or source modules."""
import difflib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .core import checkpoint
from .languages import language_for
from .ranking import resources


def formatter_for(path):
    language=language_for(path)
    if language=='python':return 'Black'
    if language=='dart':return 'Dart SDK'
    if language in {'javascript','typescript','tsx'} or Path(path).suffix.lower() in {'.json','.jsonc'}:return 'Prettier'
    return None


def format_document(path,source,cancel=None):
    checkpoint(cancel)
    if len(source.encode('utf-8'))>2_000_000:raise ValueError('Formatting is limited to documents up to 2 MB.')
    engine=formatter_for(path)
    if not engine:raise ValueError('Formatting currently supports Python, JS/JSX, TS/TSX and JSON/JSONC. Other languages retain analysis and editing.')
    started=time.monotonic()
    if engine=='Black':
        import black
        try:after=black.format_file_contents(source,fast=False,mode=black.Mode(line_length=88))
        except black.NothingChanged:after=source
        except (black.InvalidInput,AssertionError) as exc:raise ValueError('Python formatting could not be validated: '+str(exc)) from exc
    else:
        assets=resources()/'formatting';node=assets/'node.exe'
        if engine=='Prettier' and not node.is_file():raise ValueError('Bundled formatter runtime is missing. Run scripts.prepare_formatter during setup.')
        language=language_for(path)
        parser='typescript' if language in {'typescript','tsx'} else 'jsonc' if Path(path).suffix.lower()=='.jsonc' or Path(path).name in {'tsconfig.json','jsconfig.json'} else 'json' if Path(path).suffix.lower()=='.json' else 'babel'
        payload=json.dumps({'source':source,'parser':parser},ensure_ascii=False).encode('utf-8')
        env={key:value for key,value in os.environ.items() if key.upper() not in {'NODE_OPTIONS','NODE_PATH','QT_PLUGIN_PATH','QML2_IMPORT_PATH'}}
        command=[str(node),'--no-addons',str(assets/'worker.mjs')]
        if engine=='Dart SDK':
            from .flutter_sdk import detect_sdk,sdk_environment
            sdk=detect_sdk()
            if not sdk:raise ValueError('Dart formatting needs an installed Flutter/Dart SDK on PATH. Analysis and local AI remain available without it.')
            command=[str(sdk['dart']),'format','--output=show','--summary=none'];payload=source.encode('utf-8');env.update(sdk_environment())
        frozen_windows=os.name=='nt' and getattr(sys,'frozen',False)
        if frozen_windows:
            import ctypes
            ctypes.windll.kernel32.SetDllDirectoryW(None)
        try:
            process=subprocess.Popen(command,cwd=assets,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        finally:
            if frozen_windows:ctypes.windll.kernel32.SetDllDirectoryW(sys._MEIPASS)
        try:
            first=True
            while True:
                checkpoint(cancel)
                if time.monotonic()-started>15:raise ValueError('Formatter timed out after 15 seconds.')
                try:stdout,stderr=process.communicate(payload if first else None,timeout=.1);break
                except subprocess.TimeoutExpired:first=False
        except BaseException:
            process.kill();process.communicate();raise
        if process.returncode:raise ValueError('Formatting rejected this document: '+stderr.decode('utf-8','replace')[:1600])
        after=stdout.decode('utf-8').replace('\r\n','\n') if engine=='Dart SDK' else json.loads(stdout.decode('utf-8'))['formatted']
    checkpoint(cancel)
    return {'path':str(path),'before':source,'after':after,'engine':engine,'changed':after!=source,
        'seconds':time.monotonic()-started,'diff':''.join(difflib.unified_diff(source.splitlines(True),after.splitlines(True),fromfile='a/'+Path(path).name,tofile='b/'+Path(path).name)),
        'note':('Installed Dart SDK defaults · isolated stdin formatting.' if engine=='Dart SDK' else 'Built-in defaults · 88-column target · no project configuration or plugins.')+' Review the diff; tests were not run.'}
