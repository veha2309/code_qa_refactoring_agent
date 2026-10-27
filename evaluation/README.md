# Evaluation and verification

This directory contains the capability notes, evaluation methodology, pinned public-source snapshots and relevance labels. See [verification_summary.json](verification_summary.json) for a portable summary of the locally verified prototype.

Raw smoke reports, screenshots, SDK logs and build outputs are generated locally and excluded from Git because they can contain absolute paths or details from repositories opened during development. References to those reports in development notes identify local artifacts, not files shipped in this public source repository.

Reproduce the checks from the repository root after running `scripts/setup.ps1`:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:CHANGELENS_TEST_NO_AI = '1'
$env:LOCALAPPDATA = Join-Path $env:TEMP 'ChangeLensVerification'
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe launcher.py --self-test-format evaluation/formatter.json
.\.venv\Scripts\python.exe launcher.py --self-test-languages evaluation/languages.json
.\.venv\Scripts\python.exe launcher.py --self-test-workflow evaluation/workflow.json
```

To include actual local-model responses, prepare the presentation models in Ollama first, remove `CHANGELENS_TEST_NO_AI`, and add `--with-local-ai` to the workflow smoke command. Models can legitimately return no improvement; the UI retains an explicit regeneration action.

Public-source relevance evaluation uses the pinned commits in `public_snapshots.json` and annotations in `public_labels.json`. See [RESULTS.md](RESULTS.md) for measured results and limitations. These labels were source-reviewed by an agent and are partial positives, not an independent exhaustive benchmark. Public repository code is not executed by the evaluator.

```powershell
.\.venv\Scripts\python.exe -m scripts.fetch_evaluation
.\.venv\Scripts\python.exe -m scripts.public_evaluate
```

The initial fetch requires network access. Flutter SDK and real local-model checks are optional and require their separately prepared local tools. Unit-test totals include controlled fixtures; successful checks do not prove semantic equivalence, general relevance accuracy, or superiority to another coding assistant.
