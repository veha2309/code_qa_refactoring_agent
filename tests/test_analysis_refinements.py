import json
from threading import Event

import pytest

from changelens.core import Cancelled, impact_paths, index_repository, report_markdown, test_link_gaps as link_gaps
from changelens.ranking import rank_tests, resources


def write(root, path, code):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(code, encoding="utf-8")


@pytest.mark.parametrize("code,callers", [
    ("from lib import compute\ndef outer():\n    def inner():\n        compute = 3\n    return compute()\n", {"user.py:outer"}),
    ("def outer():\n    from lib import compute\n    def inner(): return compute()\n    return inner()\n", {"user.py:outer.inner"}),
    ("from lib import compute\ndef run(compute): return compute()\n", set()),
    ("from lib import compute\ndef run():\n    compute = lambda: 3\n    return compute()\n", set()),
    ("from lib import compute\ndef run():\n    import other as compute\n    return compute()\n", set()),
    ("from lib import compute\ndef outer(compute):\n    def inner(): return compute()\n    return inner()\n", set()),
    ("from lib import compute\ndef run(values):\n    return [compute() for compute in values]\n", set()),
    ("from lib import compute\ndef run():\n    return (lambda compute: compute())(None)\n", set()),
    ("from lib import compute\ndef run():\n    global compute\n    return compute()\n", {"user.py:run"}),
    ("def outer():\n    from lib import compute\n    def inner():\n        nonlocal compute\n        return compute()\n    return inner()\n", {"user.py:outer.inner"}),
    ("from lib import compute\ncompute = lambda: 3\ndef run(): return compute()\n", set()),
    ("from lib import compute\nfrom other import compute\ndef run(): return compute()\n", set()),
    ("from lib import compute\ndef run():\n    global compute\n    compute = lambda: 3\n    return compute()\n", set()),
])
def test_lexical_bindings_do_not_leak_or_invent_links(tmp_path, code, callers):
    write(tmp_path, "lib.py", "def compute(): return 1\n")
    write(tmp_path, "other.py", "def compute(): return 2\n")
    write(tmp_path, "user.py", code)
    snapshot = index_repository(tmp_path)
    assert {e["caller"] for e in snapshot.edges if e["callee"] == "lib.py:compute"} == callers


def test_unicode_identifiers_resolve(tmp_path):
    write(tmp_path, "a.py", "def मूल्य(): return 1\ndef caller(): return मूल्य()\n")
    snapshot = index_repository(tmp_path)
    assert any(e["callee"] == "a.py:मूल्य" and e["caller"] == "a.py:caller" for e in snapshot.edges)


def test_reassigned_receiver_does_not_invent_method_link(tmp_path):
    write(tmp_path, "a.py", "class Store:\n    def total(self): return 1\n    def caller(self, other):\n        self = other\n        return self.total()\n")
    snapshot = index_repository(tmp_path)
    assert not snapshot.edges


def test_autouse_fixture_is_scoped_and_links_through_helper(tmp_path):
    write(tmp_path, "helpers.py", "def connect(): return 1\n")
    write(tmp_path, "tests/conftest.py", "import pytest\nfrom helpers import connect\n@pytest.fixture(autouse=True)\ndef setup_db(): return connect()\n")
    write(tmp_path, "tests/test_a.py", "def test_one(): assert True\n")
    write(tmp_path, "other/test_b.py", "def test_other(): assert True\n")
    snapshot = index_repository(tmp_path)
    impacted = {row["symbol"] for row in impact_paths(snapshot, ["helpers.py:connect"])}
    assert "tests/test_a.py:test_one" in impacted
    assert "other/test_b.py:test_other" not in impacted
    assert any(e.get("via") == "autouse" for e in snapshot.edges)


def test_marked_fixtures_at_function_class_and_module_scope(tmp_path):
    write(tmp_path, "conftest.py", "import pytest as p\n@p.fixture\ndef db(): return 1\n")
    write(tmp_path, "test_function.py", "import pytest as p\n@p.mark.usefixtures('db')\ndef test_one(): pass\n")
    write(tmp_path, "test_class.py", "import pytest\n@pytest.mark.usefixtures('db')\nclass TestA:\n    def test_one(self): pass\nclass TestB:\n    def test_two(self): pass\n")
    write(tmp_path, "test_module.py", "from pytest import mark\npytestmark = [mark.usefixtures('db')]\ndef test_one(): pass\n")
    snapshot = index_repository(tmp_path)
    actual = {e["caller"] for e in snapshot.edges if e["callee"] == "conftest.py:db"}
    assert actual == {"test_function.py:test_one", "test_class.py:TestA.test_one", "test_module.py:test_one"}


def test_indirect_parametrization_and_fixture_override(tmp_path):
    write(tmp_path, "conftest.py", "import pytest\n@pytest.fixture\ndef value(): return 1\n")
    write(tmp_path, "tests/conftest.py", "from pytest import fixture\n@fixture\ndef value(value): return value + 1\n")
    write(tmp_path, "tests/test_a.py", "import pytest\n@pytest.mark.parametrize('value', [1], indirect=True)\ndef test_indirect(value): pass\n@pytest.mark.parametrize('value', [1])\ndef test_direct(value): pass\n")
    snapshot = index_repository(tmp_path)
    impacted = {row["symbol"] for row in impact_paths(snapshot, ["conftest.py:value"])}
    assert "tests/test_a.py:test_indirect" in impacted
    assert "tests/test_a.py:test_direct" not in impacted


def test_class_fixtures_do_not_leak_and_imported_fixture_alias_resolves(tmp_path):
    write(tmp_path, "helpers.py", "import pytest\n@pytest.fixture\ndef original(): return 1\n")
    write(tmp_path, "test_a.py", "import pytest\nfrom helpers import original as data\nclass TestA:\n    @pytest.fixture(autouse=True)\n    def local(self): return 1\n    def test_one(self, data): pass\nclass TestB:\n    def test_two(self): pass\n")
    snapshot = index_repository(tmp_path)
    assert any(e["caller"] == "test_a.py:TestA.test_one" and e["callee"] == "helpers.py:original" for e in snapshot.edges)
    assert not any(e["caller"] == "test_a.py:TestB.test_two" for e in snapshot.edges)


def test_evidence_priority_survives_adversarial_model_scores(tmp_path):
    write(tmp_path, "a.py", "def compute_total(): return 1\n")
    write(tmp_path, "test_a.py", "from a import compute_total\ndef test_real(): assert compute_total() == 1\ndef test_compute_total(): assert True\n")
    model = json.loads((resources()/"starter_model.json").read_text(encoding="utf-8"))
    model["coefficients"] = [0, 100, 0, 0, -100]
    path = tmp_path/"model.json"; path.write_text(json.dumps(model))
    snapshot = index_repository(tmp_path)
    rows = rank_tests(snapshot, ["a.py:compute_total"], model_path=path)
    assert rows[0]["symbol"] == "test_a.py:test_real"
    assert rows[0]["score"] < rows[1]["score"]
    assert not rows[1]["recommended"]
    assert rows[1]["relation"] == "Name similarity"
    fallback = rank_tests(snapshot, ["a.py:compute_total"], model_path=tmp_path/"missing.json")
    assert fallback[0]["symbol"] == rows[0]["symbol"]
    assert fallback[0]["method"] == "structural fallback"


def test_graph_cancellation_and_gap_equivalence(tmp_path):
    write(tmp_path, "a.py", "def one(): return 1\ndef two(): return one()\ndef unused(): pass\n")
    write(tmp_path, "test_a.py", "from a import two\ndef test_two(): assert two()\n")
    snapshot = index_repository(tmp_path)
    assert link_gaps(snapshot, list(snapshot.symbols)) == ["a.py:unused"]
    stop = Event(); stop.set()
    with pytest.raises(Cancelled): impact_paths(snapshot, ["a.py:one"], cancel=stop)
    with pytest.raises(Cancelled): rank_tests(snapshot, ["a.py:one"], cancel=stop)


def test_markdown_separates_unlinked_candidates_and_actual_execution():
    report = {"snapshot":"example", "impact":[], "warnings":[], "freshness":"out of date",
              "tests":[{"symbol":"test_linked", "score":.1, "method":"structural fallback", "recommended":True},
                       {"symbol":"test_unlinked", "score":.9, "method":"structural fallback", "recommended":False}],
              "test_run":{"status":"failed", "returncode":1, "tests_requested":1, "seconds":.1}}
    markdown = report_markdown(report)
    recommendations = markdown.split("## Recommended tests")[1].split("## Other candidates")[0]
    assert "test_linked" in recommendations and "test_unlinked" not in recommendations
    assert "out of date" in markdown and "Status: failed" in markdown
    assert "complete project suite was not run" in markdown
