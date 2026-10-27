# Core feature refinement

This batch focuses on impact accuracy and a reliable edit–analyze–review workflow. It does not change the synthetic training set or claim a new generative model.

Regression coverage in `tests/test_analysis_refinements.py` checks nested/local/global/nonlocal bindings, parameter and assignment shadowing, ambiguous imports, Unicode identifiers, reassigned receivers, lambda/comprehension limitations, automatic and marked pytest fixtures, indirect parameters, fixture overrides, imported fixture aliases, evidence-first test ordering even with adversarial model scores, graph cancellation, coverage-link gaps and honest Markdown reports.

UI regressions check persistent manual test selection, stale analysis/patch warnings, disabled stale actions, and preservation of stale state after a failed refresh. Extraction regressions reject existing local, parameter and enclosing names while preserving original files.

Reproduce from the project root:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:LOCALAPPDATA=Join-Path (Get-Location) '.runtime'
.\.venv\Scripts\python.exe -m pytest tests -q --basetemp .runtime/pytest-refinement-check
.\.venv\Scripts\python.exe -m scripts.public_evaluate
.\.venv\Scripts\python.exe -m scripts.demo_validation
.\.venv\Scripts\python.exe -m scripts.summarize
```

Public evaluation reads pinned source snapshots only. Its 30 partial-label function scenarios are small, curated relevance checks; they do not measure all relevant tests or runtime regression detection. Learned ranking now includes evidence-priority guardrails; compare its combined policy with the raw keyword and structural baselines. `RESULTS.md` and `public_results.json` contain measurements.

Remaining limitations: framework/dynamic dispatch, runtime monkey patches, inherited/plugin fixtures, dynamic marker expressions, and calls in anonymous scopes may be unresolved. File hashes are checked at execution/application boundaries; disk changes are not continuously watched. Passing syntax checks or selected tests does not establish behavior preservation.
