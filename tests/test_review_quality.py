import json
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from changelens.core import index_repository
from changelens.syntax import parse_unit,source_tree
from changelens.architecture import review_architecture,report_markdown
from changelens.review_quality import diagnostic_digest,cycle_witness


@pytest.mark.parametrize('attribute',['class','for','default','delete'])
def test_jsx_keyword_attributes_keep_original_source_offsets_and_references(tmp_path,attribute):
    source=f'import Card from "./Card";\nexport function Screen(value){{return <label {attribute}="example"><Card value={{value}}/></label>}}'
    unit=parse_unit('Screen.jsx',source);screen=next(s for s in unit.symbols if s.name=='Screen')
    assert source.encode()[screen.start_byte:screen.end_byte].decode()==screen.source
    assert screen.source.endswith('</label>}') and any(call[1]=='Card' for call in unit.calls)
    (tmp_path/'Screen.jsx').write_text(source);(tmp_path/'Card.jsx').write_text('export default function Card(){return <div/>}')
    snapshot=index_repository(tmp_path)
    assert not any(w.startswith('Cannot parse') for w in snapshot.warnings)
    assert any(e['caller']=='Screen.jsx:Screen' and e['callee']=='Card.jsx:Card' for e in snapshot.edges)


@pytest.mark.parametrize('source',[
    'export function Screen(x: number){return <div class="x"/>}',
    'export function Screen(){const x = value as number;return <div class="x"/>}',
    'export function Screen(value: number){return <div>Name & Address</div>}',
    'export function Screen(){const x = ;return <div class="x"/>}',
    'export function Screen(){return <div class="x">}',
    'export function Screen(){return <div>{value &}</div>}'
])
def test_jsx_compatibility_does_not_accept_typescript_or_broken_js(source):
    with pytest.raises(SyntaxError):parse_unit('Screen.jsx',source)


@pytest.mark.parametrize('source',[
    'export function Screen(){return <h2>Filter & Search</h2>}',
    'export function Screen(){return <label for="x">Name & Address</label>}',
    'export function Screen(){return <div class="x"><h2>Image & URL</h2>{value & mask}</div>}'
])
def test_raw_jsx_text_keeps_ampersands_and_does_not_change_js_expressions(source):
    unit=parse_unit('Screen.jsx',source);symbol=next(s for s in unit.symbols if s.name=='Screen')
    assert '&' in symbol.source and source.encode()[symbol.start_byte:symbol.end_byte].decode()==symbol.source
    assert not source_tree('Screen.jsx',source.encode()).root_node.has_error


def test_implicit_terminator_before_array_spread_keeps_source_bytes_and_lines():
    source='function Screen(){\n    const fetchData = async () => { return 1 }\n    [...(items || [])].sort(compare)\n    return <div/>\n}'
    unit=parse_unit('Screen.js',source)
    for symbol in unit.symbols:
        if symbol.kind!='module':assert source.encode()[symbol.start_byte:symbol.end_byte].decode()==symbol.source
    assert any(call[1]=='compare' and call[2]==3 for call in unit.calls) or any('sort' in call[1] and call[2]==3 for call in unit.calls)
    with pytest.raises(SyntaxError):parse_unit('Screen.js','function Screen(){ const f=()=>{} [...items].sort(compare) }')


def test_keyword_jsx_rewrite_checks_complete_declaration_and_signature(tmp_path):
    from changelens.local_ai import rewrite_patch
    source='export function Screen(value){const result=value;return <label for="x">{result}</label>}\n'
    (tmp_path/'Screen.jsx').write_text(source);snapshot=index_repository(tmp_path);symbol=snapshot.symbols['Screen.jsx:Screen']
    patch=rewrite_patch(snapshot,symbol,json.dumps({'code':'function Screen(value){return <label for="x">{value}</label>}','explanation':'Inline.'}))
    assert patch['syntax_validation']=='passed' and (tmp_path/'Screen.jsx').read_text()==source
    with pytest.raises(ValueError):rewrite_patch(snapshot,symbol,json.dumps({'code':'function Screen(changed){return <label for="x">{changed}</label>}'}))


def test_diagnostic_counts_do_not_conflate_parser_dynamic_and_asset_imports():
    warnings=['Cannot parse bad.js: javascript syntax error near line 4',
        'Unresolved local module ./theme.css imported by Screen.jsx','Unresolved local module ./missing imported by Screen.jsx',
        'Unresolved call/reference Screen.jsx:3: console.log (external, dynamic, shadowed or ambiguous)',
        'Unresolved call/reference Screen.jsx:4: setItems (external, dynamic, shadowed or ambiguous)',
        'Unresolved call/reference Another.jsx:8: setItems (external, dynamic, shadowed or ambiguous)']
    data=diagnostic_digest(warnings);assert data['raw_occurrences']==6
    assert data['counts']=={'parser exclusions':1,'non-source resource imports':1,'unresolved local imports':1,'global-shaped references':1,'dynamic / external references':2}
    group=next(g for g in data['groups'] if g['title']=='setItems');assert group['count']==2 and group['file_count']==2
    assert next(g for g in data['groups'] if g['category']=='parser exclusions')['examples'][0]['line']==4


def test_review_has_closed_source_witness_next_step_and_groups_threshold_metrics(tmp_path):
    (tmp_path/'app.js').write_text("// entry\n\nimport {work} from './controller.js';\nexport function main(){return work()}\n")
    (tmp_path/'controller.js').write_text("// helper\nimport {main} from './app.js';\nexport function work(){return main()}\n")
    for i in range(8):(tmp_path/f'long{i}.py').write_text('def large():\n'+''.join('    value = 1\n' for _ in range(90)))
    report=review_architecture(index_repository(tmp_path));review=report['review']
    assert review['metrics']['large_definitions']>=8 and not any(i['kind']=='large_definition' for i in review['items'])
    cycle=next(i for i in review['items'] if i['kind']=='dependency_cycle');witness=cycle['evidence']
    assert witness[0]['from']==witness[-1]['to']
    assert {(e['path'],e['line']) for e in witness}=={('app.js',3),('controller.js',2)}
    assert all(a['to']==b['from'] for a,b in zip(witness,witness[1:])) and cycle['next_step']
    text=report_markdown(report)
    assert 'Next step:' in text and 'app.js:3' in text and '## Analysis coverage' in text
    assert '## Recorded symbol relationships' not in text and len(text)<15000


def test_review_source_navigation_and_grouped_coverage_filter(tmp_path,monkeypatch):
    from changelens.architecture_ui import ArchitectureView
    from changelens.review_quality import build_review
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'settings'))
    report=review_architecture(index_repository(tmp_path));report['warnings']=[f'Unresolved call/reference file{i}.jsx:4: setItems (external, dynamic, shadowed or ambiguous)' for i in range(5000)]+['Cannot parse broken.js: parser limitation']
    report['review']=build_review(report)
    app=QApplication.instance() or QApplication([]);view=ArchitectureView();view.set_report(report)
    assert 'parser exclusions' in view.overview.toPlainText() and 'heuristic findings' not in view.overview.toPlainText()
    assert view.coverage_rows.topLevelItemCount()==2
    view.coverage_query.setText('setItems');assert view.coverage_rows.topLevelItemCount()==1
    assert '5000 / 5000 files'==view.coverage_rows.topLevelItem(0).text(1)
    view.coverage_query.setText('file4999.jsx');assert view.coverage_rows.topLevelItemCount()==1
    assert 'file4999.jsx' in view.coverage_rows.topLevelItem(0).child(0).text(0)
    view.coverage_query.clear();child=view.review_items.topLevelItem(0).child(0);opened=[];view.codeRequested.connect(lambda p,l:opened.append((p,l)))
    view.open_review_item(child);assert opened==[('broken.js',1)]
    view.close();app.processEvents()


def test_generated_endpoint_metadata_redacts_credentials_and_keeps_useful_query(tmp_path):
    from changelens.feature_flows import public_url
    assert public_url('https://example.invalid/data?appid=literal-key&lang=all')=='https://example.invalid/data?appid=[redacted]&lang=all'
    assert 'pass' not in public_url('https://user:pass@example.invalid/data?api_key=credential')
    (tmp_path/'client.jsx').write_text("import axios from 'axios';export async function load(){return axios.get('https://example.invalid/data?token=private-value&lang=all')}")
    report=review_architecture(index_repository(tmp_path));flow=report['feature_flows']['flows'][0]
    assert 'private-value' not in json.dumps(flow) and '[redacted]' in flow['url'] and 'lang=all' in flow['url']


def test_unresolved_local_import_retains_the_real_source_line(tmp_path):
    (tmp_path/'screen.js').write_text('// header\n\nimport Thing from "./missing";\nexport function Screen(){return Thing()}')
    digest=diagnostic_digest(index_repository(tmp_path).warnings)
    example=next(g for g in digest['groups'] if g['category']=='unresolved local imports')['examples'][0]
    assert example['path']=='screen.js' and example['line']==3
