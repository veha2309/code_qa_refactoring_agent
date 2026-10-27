"""Fixed worker for trusted bundled demo, used by source and frozen builds."""
import json
import os
from pathlib import Path
import sys


def main(args=None):
    args = list(sys.argv[1:] if args is None else args)
    root, output, *nodes = args
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    os.chdir(root)
    sys.path.insert(0, root)
    import pytest
    outcomes = []

    class Recorder:
        def pytest_runtest_logreport(self, report):
            if report.when == "call" or report.failed:
                outcomes.append({"nodeid": report.nodeid, "outcome": report.outcome, "phase": report.when})

    config = Path(root) / "pytest.ini"
    config.write_text("[pytest]\n", encoding="utf-8")
    result = pytest.main(["-q", "-c", str(config), "--rootdir", root, "--confcutdir", root, "-p", "no:cacheprovider", *nodes], plugins=[Recorder()])
    Path(output).write_text(json.dumps(outcomes), encoding="utf-8")
    return result


if __name__ == "__main__":
    raise SystemExit(main())

