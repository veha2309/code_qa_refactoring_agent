# Change Lens QA MVP verification

Windows development host, 5 November 2026. The Qt workbench was exercised with isolated application data and disposable projects.

## Regression and sample checks

The regression suite covers source evidence, removed declarations, parser errors, test linkage, rejected model citations, unsaved buffers, cancellation, project switching, missing runners, stale previews, partial patch writes, and conflict-checked undo. Stubbed model responses exercise the UI and validation contract.

The final full suite passed **276 tests** in 111.89 seconds, including the four live cases, with 12 existing Rope deprecation warnings.

A fresh app profile opened the bundled sample, selected `calculate_invoice_total` from the Review picker, previewed and applied a Rope rename, and ran five linked pytest tests. All five passed. Undo restored the original source bytes.

## Live model and actual test runners

The four opt-in walkthroughs use the installed `qwen2.5-coder:3b` Ollama model. Each clean control displayed zero supported findings. The model proposed candidates on clean code, and the source checks discarded them. Each seeded case identified the changed fee operation using the saved and baseline excerpts. These cases measure one controlled regression across language adapters. The displayed findings are model interpretations.

On 6 November 2026, all four live walkthroughs passed with **Preview fix** launched directly from the finding. The same selected test failed before the fix and passed after it. Undo restored the pre-fix bytes.

One intermediate TSX run failed at undo after Vitest. The isolated rerun and both subsequent full runs passed.

| Fixture | Runner | Seeded regression | After applying the proposed fix | Undo |
| --- | --- | --- | --- | --- |
| Python | pytest | Selected test failed | Selected test passed | Original bytes restored |
| JavaScript | Node | Selected file failed | Selected file passed | Original bytes restored |
| TypeScript and TSX | Vitest | Selected file failed | Selected file passed | Original bytes restored |
| Dart and Flutter | Flutter SDK | Selected file failed | Selected file passed | Original bytes restored |

To reproduce, use a fresh writable pytest base outside any Git checkout or set the Git ceiling to the temporary directory's parent. Use a local Ollama service with the review model installed, Node, a fixture directory with installed Vitest and React, and a prepared Flutter sample with its generated package metadata. The verification fixtures use the supplied dependencies and run after the trust prompt.

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:CHANGELENS_TEST_NO_AI = '1'
$env:CHANGELENS_MVP_LIVE = '1'
$env:CHANGELENS_MVP_VITEST = 'C:\path\to\prepared-vitest-fixture'
$env:CHANGELENS_MVP_FLUTTER = 'C:\path\to\prepared-flutter-sample'
.\.venv\Scripts\python.exe -m pytest -q -s tests/test_qa_mvp.py -k live_qa
```

## Windows profile

The mixed development checkout had 317 indexed files and roughly 8,700 declarations. A diagnostic run spent 53.8 seconds in Git comparison, including repeated AST parsing of surviving files after a deletion. Reusing a single parse per file cut the observed comparison to 3.4 seconds. The updated run measured 2.8 seconds for indexing, 12.7 seconds for the complete saved review worker, and 1.9 seconds for the Qt review refresh. These are local observations from a dirty checkout. The Python change addressed the identified bottleneck.
