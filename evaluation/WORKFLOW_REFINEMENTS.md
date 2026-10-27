# Import, editor, Lens, search, AI and Flutter refinements

Latest executable: `dist/workflow/ChangeLens/ChangeLens.exe`. Keep its entire directory together.

## HydroNexus import

The failure was reproduced against the local HydroNexus repository. Indexing included bundled `.python-packages` dependencies, then reparsed valid indented methods as standalone dedented fragments. Flush-left lines inside multiline strings made those fragments invalid even when the original files were valid Python.

Indexing now reuses original full-file Python AST nodes, including classes used by pytest fixture analysis. UI helpers inspect indented definitions without rewriting literal whitespace. Dependency/cache folders such as `.python-packages`, `site-packages`, `.dart_tool` and `.pub-cache` are excluded. Invalid source files retain file-specific warnings while other files continue indexing.

Read-only HydroNexus verification: **99 indexed files, 581 symbols, 1,321 relationships, zero syntax issues**. No repository modules or tests were executed and no source files were changed. Report: `hydronexus_import.json`.

## Typing and motion

Git revision/diff commands now use Windows `CREATE_NO_WINDOW`. This is the direct fix for the rapidly appearing/disappearing console windows during automatic project checks. Formatter, demo/test runner and cancellation helpers also launch hidden. A Windows regression test queries a real child process's attached console handle to verify that no console is created.

- Cursor movement reuses per-file symbols and cached suggestions instead of rescanning every project symbol and reparsing definitions on each keystroke.
- Tab respects indentation stops. Tab/Shift+Tab indent/unindent selected lines in one undoable edit. Backspace removes one indentation level while in leading whitespace. Newline uses text before the cursor, understands Python suite colons/comments and brace pairs, and defaults to two spaces for JS/TS/Dart and four for Python. Existing consistent tabs/spaces are detected when loading documents.
- Automatic name completion does not consume Enter for the default suggestion. Tab accepts it; explicitly requested or keyboard-selected suggestions may use Enter. Local model ghost suggestions retain Tab/Escape behavior. Explicit Jedi completion remains Ctrl+Space.
- A small navigation marker glides for 160 ms; page content switches directly without old-page snapshots or content fades. The evidence drawer fades in, and map nodes have short hover feedback. No continuous animation loop or blur is applied to live editor text.
- Opening/closing editor tabs and applying analysis updates batch painting atomically. The file tree is reused when paths/top-level symbols are unchanged; rebuilt trees retain expansion, selection and scroll position. Background analysis preserves the active page and tab. This avoids intermediate blank states and the visual flash of repeated tree reconstruction.
- **View → Reduce motion** remembers the preference. `CHANGELENS_REDUCE_MOTION=1` also disables transitions.

## Lens relationships and changes

The old map collected edges only from one shortest-path witness per affected symbol. It could omit a second valid route into a shared caller, as in AuthCard → LoginScreen/RegisterScreen → App. The map now retains all recorded relationships between visible affected symbols, draws separate same-column lanes, and highlights alternate routes when inspecting a shared caller. The evidence drawer describes one witness path; exported relationships retain additional routes.

The actual StockPulse repository was checked read-only. Both AuthCard-to-screen links and both screen-to-App links are now retained. Report: `stockpulse_auth_paths.json`.

After edits, **all project symbols remain in the focus picker**. Changed symbols are marked. Multiple changed symbols offer **All changes**, with separate real starting nodes rather than invented call relationships. A single focus still traces transitive callers across files. Up to 36 nodes are displayed, with omitted counts and complete detailed evidence. Static analysis still cannot infer arbitrary dynamic references or prove breakage.

## Visible search results

- **Ctrl+F:** live case-insensitive literal search in the current buffer, match highlighting, current/total counts, previous/next controls, **Aa** case matching and an explicit no-match state. Enter/F3 moves forward; Shift+Enter/Shift+F3 moves backward; Escape closes search. Editing with search open refreshes highlights without moving the typing cursor.
- **Ctrl+Shift+F:** project text search with filenames, line numbers, matching text and result counts. Open unsaved buffers are included. Double-click opens the result. Project search is case-insensitive literal text, bounded to 500 results, 10,000 candidate files, 32 MB total text and 2 MB per file. Exclusions, symlink boundaries and unreadable files are respected; limits/skips are disclosed.
- **Ctrl+P** continues to search filenames. A text query absent from the current file can use **Search project** directly from the find bar.

## Reviewed AI suggestions across languages

Local completion/explanations and **Local AI suggested improvement → Regenerate suggestion** now support indexed Python, JS/JSX, TS/TSX, Java, C#, Go, Rust and Dart declarations. Tree-sitter languages use exact declaration byte spans, whole-result syntax validation, signature/modifier/name checks and import/dependency-loading checks. Existing exports, surrounding code and annotations outside the selected span are preserved. Multiple or ambiguous declarations and unsupported body forms are rejected.

The 3B assistant retains the 3,500-character focused-input limit. Python uses its existing AST checks. Model proposals remain unverified for types, runtime behavior and semantic equivalence. No proposed code is executed during generation. Reviewed application retains freshness/content checks and recoverable backups. **Structural rename/extract and static Jedi definition navigation remain Python-only.** Regeneration is explicit, not triggered repeatedly by hidden field updates.

An explicit **No new improvement returned** response is valid; the app does not force a model to change already clear code. The review mode and regeneration action remain available after that response. Rejected/unchanged model responses do not modify source.

Controlled tests cover all supported declaration adapters. Actual local-model TypeScript generation and regeneration also passed without modifying source. This does not establish broad per-language model quality or performance on the presentation laptop.

## Flutter/Dart

Bundled Dart syntax parsing, highlighting, source diffs, search, declarations, straightforward local/package imports/exports, prefix aliases, constructors and literal `test`/`testWidgets` declarations work without Flutter installed. `pubspec.yaml` identifies the package name and standard Flutter SDK dependency. The Lens labels `build`/`createState` composition as **Flutter inference**, connecting widget classes through build methods and into tests where references are visible.

Flutter navigation, provider/DI wiring, full type resolution, dynamic dispatch, parts/conditional libraries, named constructors and newer grammar constructs can remain unresolved. This is not a Dart analyzer, Flutter debugger, hot-reload host or emulator manager. Unsupported syntax is reported; generated code/build caches are excluded. Non-Python ranking remains structural.

- **Formatting** uses a Flutter/Dart SDK already on PATH, or `FLUTTER_ROOT`. It feeds the current buffer to `dart format` through stdin in an isolated directory, uses SDK defaults and returns the normal preview/undo workflow. The SDK is not bundled or downloaded. Missing SDK produces an explicit message; analysis/local AI remain available.
- **Tests** use a prepared Flutter SDK, cached Windows tester/tool artifacts and existing project `.dart_tool/package_config.json`. Selected test files run only after repository trust, with timeout, cancellation and captured output. All tests in those files may run. The app invokes the SDK executable directly, passes `--no-pub`, suppresses SDK analytics, and blocks SDK artifact/pub downloads via loopback hosts. Incomplete preparation fails rather than downloading dependencies. Flutter may print the loopback artifact-host notice. Standalone Dart package test execution is not included.
- **Project: Open Flutter sample** in Ctrl+Shift+P creates an editable sample with AuthCard shared by login/register screens and two widget tests. Prepare its SDK/dependencies yourself before offline test runs; the app does not run `pub get` or `flutter run`.

The bundled example was prepared in a disposable workspace copy with **offline cached dependency resolution** and executed with the installed Flutter SDK: **both widget tests passed**. The Dart formatter was also exercised. No external repository code was executed. Report: `flutter_sdk_validation.json`.

## Verification

The full suite covers the import regression, multiline literals, excluded dependencies, cross-file and alternate paths, changed/all-project focus, typing and completion keys, live/project search, motion completion/reduction, exact-span AI proposals across languages, actual TypeScript regeneration and Flutter composition/test discovery/formatter/runner guards.

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:LOCALAPPDATA=Join-Path (Get-Location) '.runtime'
.\.venv\Scripts\python.exe -m pytest tests -q --basetemp .runtime/workflow-verification
.\.venv\Scripts\python.exe launcher.py --self-test-workflow evaluation/source_smoke_workflow.json --with-local-ai
```

`--with-local-ai` requires the existing presentation models in the local Ollama service. Omit it for controlled checks without model inference. The Windows executable exposes the same `--self-test-workflow` flag. Existing language, formatter and Python/local-AI smoke checks remain available.

## Release checks

- Full suite: **167 passed**, with 12 existing Rope deprecation warnings. Includes the real Windows child-console probe and stable tab/refresh regression tests. Output: `workflow_pytest.txt`.
- Final frozen workflow smoke: **12 checks passed**, including bundled Dart parsing, installed SDK formatting, alternate/cross-file graph paths, visible search results, typing, stable navigation and actual TypeScript AI generation/regeneration responses. Report: `packaged_workflow_workflow.json`.
- Final frozen core/demo smoke: **passed through stage 6**. Formatter smoke: **6 checks passed**. Language smoke: **11 checks passed**. Reports: `packaged_workflow_core.json`, `packaged_workflow_format.json`, `packaged_workflow_languages.json`.
- Final frozen Python/local-model smoke: **passed through stage 13**, including real inline autocomplete, a checked Python rewrite preview and a focused evidence brief. Report: `packaged_workflow_ai.json`.
- The actual HydroNexus and StockPulse repositories and the controlled Flutter sample were opened in the native UI without executing repository code. Report: `native_project_checks.json`.
- Both controlled Flutter widget tests passed using a prepared installed SDK and cached dependencies. Report: `flutter_sdk_validation.json`.

Save unsaved work and close older Change Lens instances before opening the updated executable. An already running old copy retains its previous subprocess-launch behavior.
