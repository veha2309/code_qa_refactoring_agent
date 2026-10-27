# Prototype evaluation results

Measured on the current development machine. These results are not a Copilot comparison.

## Public source relevance

30 source-reviewed function-selection cases, ten per repository. Each case has a partial annotated positive set; Recall@5 is over these annotations, not all genuinely relevant tests. No public repository code was executed. These are static relevance results, not observed regression detection.

| Repository | Method | Indexed cases | Annotated Recall@5 | MRR | Ranking seconds |
|---|---|---:|---:|---:|---:|
| requests | keyword | 10/10 | 0.800 | 0.818 | 0.270 |
| requests | structural | 10/10 | 1.000 | 1.000 | 0.270 |
| requests | learned | 10/10 | 1.000 | 1.000 | 0.286 |
| flask | keyword | 10/10 | 0.100 | 0.056 | 0.336 |
| flask | structural | 10/10 | 1.000 | 0.900 | 0.338 |
| flask | learned | 10/10 | 1.000 | 0.833 | 0.359 |
| click | keyword | 10/10 | 0.300 | 0.173 | 0.552 |
| click | structural | 10/10 | 1.000 | 0.808 | 0.518 |
| click | learned | 10/10 | 1.000 | 0.875 | 0.576 |

All 30 scenarios have indexed identifiers. A supported identifier does not imply fully resolved runtime dependencies. Each case records whether an annotated test had a resolved static path. Calls through nested functions, fixtures, reflection and dynamically typed objects remain incomplete.

The learned method includes an evidence-first policy: resolved dependencies precede inferred dependencies, followed by name-only and weak candidates. Model scores order tests within these groups. These results evaluate that combined policy, not the logistic model in isolation. Name-only candidates are not selected for execution by default.

Timing excludes ingestion and UI rendering. Memory figures in JSON measure traced Python allocations during ranking, excluding native allocations and total process memory.

## Controlled demo execution

- baseline: selected suite passed; full suite passed; observed failing-test recall None.
- rename: selected suite passed; full suite passed; observed failing-test recall None.
- controlled_mutation: selected suite failed; full suite failed; observed failing-test recall 1.0.

The tax mutation is synthetic. It produced four observed failures, all caught by the selected suite. Ordinary and renamed demo copies passed all seven full-suite tests. Passing tests do not prove behavior preservation.

## Model limitations

The logistic-regression starter model uses 80 synthetic training pairs, including 12 positives. The evaluation repository labels were not used for training. Function-level scenarios and easily identifiable positive tests favor static and lexical matching; a larger independently reviewed dataset of real changes is needed before claiming generalization or superiority.

See public_snapshots.json for pinned commits, public_labels.json for annotations, and public_results.json for per-case results and unresolved-call warnings.
