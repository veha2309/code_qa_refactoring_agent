from pathlib import Path
import json

from changelens.core import index_repository, rename_local
from changelens.ranking import rank_tests, resources
from changelens.demo import execute_demo

if __name__ == "__main__":
    root = resources() / "demo"
    snapshot = index_repository(root)
    ranking = rank_tests(snapshot, ["invoice.py:calculate_invoice_total"])
    selected = [row["symbol"].replace(":", "::", 1) for row in ranking[:5]]
    patch = rename_local(snapshot, "invoice.py:calculate_invoice_total", "subtotal", "net_amount")
    results = {"baseline": execute_demo(root, selected), "rename": execute_demo(root, selected, patch),
               "controlled_mutation": execute_demo(root, selected, mutation=True)}
    output = Path("evaluation/demo_validation.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))

