import json
import shutil
from pathlib import Path
import pytest
from changelens.core import index_repository,impact_paths,ensure_fresh
from changelens.local_ai import rewrite_patch
from changelens.ranking import resources,rank_tests
from changelens.js_runner import execution_family
from changelens.runner import run_project_tests
from changelens.formatting import format_document
from test_core import write


def flutter_project(root):
    shutil.copytree(resources()/'flutter_demo',root,dirs_exist_ok=True)
    return index_repository(root)


def test_flutter_widgets_package_imports_and_tests(tmp_path):
    snap=flutter_project(tmp_path)
    assert any(h['name']=='Flutter' for h in snap.profile['frameworks'])
    impact=impact_paths(snap,['lib/auth_card.dart:AuthCard']);ids={r['symbol'] for r in impact}
    assert {'lib/screens.dart:LoginScreen','lib/screens.dart:RegisterScreen','lib/main.dart:DemoApp'}<=ids
    tests=[s.id for s in snap.symbols.values() if s.is_test];assert len(tests)==2 and set(tests)<=ids
    assert execution_family(snap,tests)=='dart'
    assert any(e['kind']=='flutter_build' for e in snap.edges)
    assert all('structural ranking' in row['method'] for row in rank_tests(snap,['lib/auth_card.dart:AuthCard']))


def test_dart_import_alias_export_show_hide_and_parameter_shadow(tmp_path):
    write(tmp_path,'lib/a.dart','int calc() => 1; class Card {}')
    write(tmp_path,'lib/barrel.dart',"export 'a.dart' show calc;")
    write(tmp_path,'lib/use.dart',"import 'barrel.dart'; import 'a.dart' as a; int run() => calc(); int other() => a.calc(); int blocked(int Function() calc) => calc(); Widget view() => const a.Card();")
    snap=index_repository(tmp_path)
    assert any(e['caller']=='lib/use.dart:run' and e['callee']=='lib/a.dart:calc' for e in snap.edges)
    assert any(e['caller']=='lib/use.dart:other' and e['callee']=='lib/a.dart:calc' for e in snap.edges)
    assert not any(e['caller']=='lib/use.dart:blocked' and e['callee']=='lib/a.dart:calc' for e in snap.edges)
    assert any(e['caller']=='lib/use.dart:view' and e['callee']=='lib/a.dart:Card' for e in snap.edges)


def test_dart_syntax_exclusions_and_config_freshness(tmp_path):
    write(tmp_path,'a.dart','int total(int n) => n + 1;');write(tmp_path,'broken.dart','class {')
    write(tmp_path,'.dart_tool/generated.dart','invalid {{{')
    snap=index_repository(tmp_path);assert 'a.dart:total' in snap.symbols and '.dart_tool/generated.dart' not in snap.hashes
    assert any('broken.dart' in w for w in snap.warnings)
    write(tmp_path,'pubspec.yaml','name: demo\n')
    with pytest.raises(ValueError):ensure_fresh(snap)


def test_dart_ai_proposals_keep_signature_and_annotation(tmp_path):
    write(tmp_path,'a.dart','class A { @override int total(int n) { final value = n + 1; return value; } }')
    snap=index_repository(tmp_path);symbol=snap.symbols['a.dart:A.total']
    patch=rewrite_patch(snap,symbol,json.dumps({'code':'int total(int n) => n + 1;'}))
    assert '@override int total(int n)' in patch['files'][0]['after'] and patch['syntax_validation']=='passed'
    with pytest.raises(ValueError):rewrite_patch(snap,symbol,json.dumps({'code':'int total(String n) => 1;'}))


def test_dart_formatter_reports_missing_optional_sdk(monkeypatch):
    import changelens.flutter_sdk as sdk
    monkeypatch.setattr(sdk,'detect_sdk',lambda:None)
    with pytest.raises(ValueError,match='installed Flutter/Dart SDK'):format_document('a.dart','int total()=>1;')


def test_flutter_runner_requires_trust_and_prepared_sdk(tmp_path,monkeypatch):
    import changelens.flutter_sdk as sdk
    snap=flutter_project(tmp_path/'project');ids=[s.id for s in snap.symbols.values() if s.is_test]
    with pytest.raises(ValueError,match='trusted'):run_project_tests(snap,ids,'',False)
    sdkroot=tmp_path/'sdk'
    for path in ['bin/cache/flutter_tools.snapshot','packages/flutter_tools/.dart_tool/package_config.json','bin/cache/artifacts/engine/windows-x64/flutter_tester.exe','bin/cache/dart-sdk/bin/dart.exe']:write(sdkroot,path,'fixture never executed')
    write(Path(snap.root),'.dart_tool/package_config.json','{}')
    monkeypatch.setattr(sdk,'detect_sdk',lambda interpreter='':{'dart':sdkroot/'bin/cache/dart-sdk/bin/dart.exe','flutter':sdkroot})
    command,cwd,scope,count=sdk.flutter_command(snap,ids)
    assert '--no-pub' in command and '--suppress-analytics' in command and count==1
    assert not any(item.endswith('.bat') for item in command) and 'selected test files' in scope


def test_real_dart_format_if_sdk_available():
    from changelens.flutter_sdk import detect_sdk
    if not detect_sdk():pytest.skip('Flutter/Dart SDK is optional')
    result=format_document('a.dart','int total(int n){return n+1;}')
    assert result['changed'] and 'return n + 1;' in result['after']
    assert not format_document('a.dart',result['after'])['changed']


def test_dart_ai_preserves_async_modifier(tmp_path):
    write(tmp_path,'a.dart','Future<int> total(int n) async { return n + 1; }')
    snap=index_repository(tmp_path)
    with pytest.raises(ValueError):rewrite_patch(snap,snap.symbols['a.dart:total'],json.dumps({'code':'Future<int> total(int n) { return Future.value(n + 1); }'}))
