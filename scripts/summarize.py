"""Summarize measured artifacts without inventing results or ground truth."""
import json
from pathlib import Path

if __name__ == "__main__":
    results = json.loads(Path("evaluation/public_results.json").read_text(encoding="utf-8"))
    lines = ["# Prototype evaluation results", "", "Measured on the current development machine. These results are not a Copilot comparison.", "",
             "## Public source relevance", "", "30 source-reviewed function-selection cases, ten per repository. Each case has a partial annotated positive set; Recall@5 is over these annotations, not all genuinely relevant tests. No public repository code was executed. These are static relevance results, not observed regression detection.", "",
             "| Repository | Method | Indexed cases | Annotated Recall@5 | MRR | Ranking seconds |", "|---|---|---:|---:|---:|---:|"]
    for repository, report in results.items():
        for row in report["results"]:
            lines.append(f"| {repository} | {row['effective_method']} | {row['supported']}/10 | {row['recall_at_5']:.3f} | {row['mrr']:.3f} | {row['seconds']:.3f} |")
    lines += ["", "All 30 scenarios have indexed identifiers. A supported identifier does not imply fully resolved runtime dependencies. Each case records whether an annotated test had a resolved static path. Calls through nested functions, fixtures, reflection and dynamically typed objects remain incomplete.",
              "", "The learned method includes an evidence-first policy: resolved dependencies precede inferred dependencies, followed by name-only and weak candidates. Model scores order tests within these groups. These results evaluate that combined policy, not the logistic model in isolation. Name-only candidates are not selected for execution by default.",
              "", "Timing excludes ingestion and UI rendering. Memory figures in JSON measure traced Python allocations during ranking, excluding native allocations and total process memory.",
              "", "## Controlled demo execution", ""]
    validation = json.loads(Path("evaluation/demo_validation.json").read_text(encoding="utf-8"))
    for label, report in validation.items():
        lines.append(f"- {label}: selected suite {report['selected']['status']}; full suite {report['full']['status']}; observed failing-test recall {report['failing_test_recall']}.")
    lines += ["", "The tax mutation is synthetic. It produced four observed failures, all caught by the selected suite. Ordinary and renamed demo copies passed all seven full-suite tests. Passing tests do not prove behavior preservation.",
              "", "## Model limitations", "", "The logistic-regression starter model uses 80 synthetic training pairs, including 12 positives. The evaluation repository labels were not used for training. Function-level scenarios and easily identifiable positive tests favor static and lexical matching; a larger independently reviewed dataset of real changes is needed before claiming generalization or superiority.",
              "", "See public_snapshots.json for pinned commits, public_labels.json for annotations, and public_results.json for per-case results and unresolved-call warnings."]
    Path("evaluation/RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
