# Code QA & Refactoring Agent — Change Lens

A native Windows application for exploring **potential code-change impact**, inspecting dependency evidence, recommending tests, and reviewing refactoring proposals. Built with Python and PySide6, with local analysis and optional local coding models.

The main workflow is the **Lens**: select a function or review saved changes, follow affected code across files, inspect the evidence, then choose tests or review a proposed patch.

## Features

- **Change investigation:** automatic Git HEAD comparison (staged and unstaged tracked changes), untracked additions, or a saved first-open baseline for non-Git folders.
- **Evidence-driven Lens:** direct/transitive references, alternate routes into shared callers, cross-file paths, an all-changes view, and access to unchanged project symbols after edits. Inferences and unresolved references stay visible.
- **Native editor:** syntax color, paired diffs, contextual indentation, block indent/unindent, undoable formatting, file search with counts/highlights, and project search with file/line results.
- **Test recommendations:** static test discovery and structural ranking. Python also has a starter logistic-regression model trained from scratch on controlled synthetic relevance examples. Scores are rankings, not confidence percentages.
- **Reviewed refactoring:** Python rename/extract operations and bounded local-AI proposals for supported named functions/methods across languages. Proposals receive syntax/signature checks, a diff preview, freshness checks and recoverable backups before explicit application.
- **Offline formatting:** bundled Black and Prettier; an installed Dart SDK supplies Dart formatting. Formatting changes the editor in one undoable step before explicit saving.
- **Optional local AI:** Ollama-based inline completion, focused explanations and reviewed suggestions/regeneration. No paid API key is required.
- **Minimal glass-style interface:** opaque code panels, subtle navigation/hover/drawer motion, a reduced-motion setting, stable tab refreshes and hidden Windows helper processes.

## Language and framework coverage

| Language | Analysis | Test execution after trust | Structural refactoring |
| --- | --- | --- | --- |
| Python | AST references, aliases, callers, classes and supported pytest fixture relationships | Selected pytest tests | Rename/extract with Rope |
| JavaScript / JSX, TypeScript / TSX | Lexical references, local imports/exports, CommonJS, re-exports, JSX references and straightforward config aliases | Existing Node runner or installed Jest/Vitest; files or filters | AI proposals; rename/extract unavailable |
| Dart / Flutter | Declarations, local/package imports, constructors, widget references and labeled build/createState inferences | Selected Flutter test files with a prepared SDK and dependencies | AI proposals; rename/extract unavailable |
| Java, C#, Go, Rust | Conservative structural file/module/package relationships and declarations | Recommendations only | AI proposals; rename/extract unavailable |

Framework dependency declarations identify common Python, React/Next.js/Node, Java, .NET, Go, Rust and Flutter stacks. **Detection is not complete framework support.** Dynamic dispatch, routing, dependency injection, templates, conditional libraries and language-specific constructs can remain unresolved. Vue/Svelte component files and several other languages are not parsed.

Read [current capabilities and workflow details](evaluation/WORKFLOW_REFINEMENTS.md) and [multi-language boundaries](evaluation/MULTILANGUAGE.md).

## Quick start on Windows

Requirements: Windows x64, Git, Python 3.10+ and an initial internet connection for free dependencies and pinned formatter assets. The application then performs ordinary indexing/editing/formatting offline. This repository contains source, not a prebuilt executable.

```powershell
git clone https://github.com/veha2309/code_qa_refactoring_agent.git
cd code_qa_refactoring_agent
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
.\.venv\Scripts\python.exe launcher.py
```

Alternatively, double-click **Start Change Lens.cmd** after setup. The setup script creates a virtual environment, installs `requirements-lock.txt`, prepares missing formatter assets and trains the starter relevance model.

Try **Open sample project**, or use **Ctrl+Shift+P** to select **Project: Open web sample** or **Project: Open Flutter sample**. Sample copies preserve your edits under the current Windows user's application-data directory.

### Useful shortcuts

| Shortcut | Action |
| --- | --- |
| Ctrl+O / Ctrl+P | Open a project folder / find a file |
| Ctrl+F / Ctrl+Shift+F | Find in the current buffer / search project text |
| Ctrl+Shift+P | Command palette |
| Alt+Shift+F | Preview document formatting |
| Ctrl+Space | Static Python completion |
| Ctrl+Enter | Request local-model completion |
| Tab / Escape | Accept / dismiss a local inline proposal |
| Ctrl+1 | Return to the editor |

## Optional tools

**Coding models:** install Ollama separately and prepare models from **Brief → Model settings**. The presentation preset uses `qwen2.5-coder:1.5b-base` for completion and `qwen2.5-coder:3b` for briefs/proposals, with a 2,048-token context and one app-managed model active at a time. It targets a 16 GB RAM / 4 GB GPU laptop; actual performance must be checked on that machine. Initial model downloads require internet. Model weights and Ollama are not redistributed here.

**Project tests:** Python needs the project's interpreter/dependencies and pytest. JS/TS needs Node and the project's existing test tooling. Flutter formatting/testing needs an installed SDK; Flutter tests additionally require prepared cached tools and project dependencies. The app does not install packages, invoke npm scripts, run pub get, launch an emulator or execute tests on folder open.

Tests run only after an explicit action and repository trust. JS/TS/Flutter selection can execute all tests in selected files; Vitest filters may match additional files. Running tests executes trusted repository code and plugins on your machine.

## Validation and evaluation

The latest development verification recorded **167 passing automated tests**, native packaged smoke checks, and two passing controlled Flutter widget tests. See [portable verification summary](evaluation/verification_summary.json) and [reproduction commands](evaluation/README.md).

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:CHANGELENS_TEST_NO_AI = '1'
$env:LOCALAPPDATA = Join-Path $env:TEMP 'ChangeLensVerification'
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m scripts.train
.\.venv\Scripts\python.exe -m scripts.evaluate
```

Training uses versioned controlled examples in `resources/training_labels.json` and `resources/training_repo`. Public evaluation uses pinned Requests, Flask and Click snapshots with 30 partial, agent-reviewed function-selection scenarios. It is Python-only and does not execute those repositories. These results are not an independent regression benchmark or a comparison with Copilot. The optional coding LLMs are pretrained; only the relevance ranker is trained from scratch by this project.

## Build a Windows folder bundle

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build.ps1 -OutputDirectory dist/workflow
```

Output: `dist/workflow/ChangeLens/ChangeLens.exe`. **Distribute the complete ChangeLens directory.** The unsigned prototype has no installer. The build collects resources and license notices, and its runtime handling addresses the earlier Qt DLL-loading issue. Generated executables, environments, caches and machine-specific reports are excluded from Git.

The large Node formatter runtime is prepared locally by `scripts/prepare_formatter.py` using pinned official sources and integrity checks. Its executable is deliberately excluded from this source repository; setup restores it before use/build.

## Source layout

| Directory | Purpose |
| --- | --- |
| `changelens/` | Native UI, editor, indexing, snapshots, language adapters, impact tracing, ranking, search, AI/patch services and test runners |
| `resources/` | Controlled Python/web/Flutter samples, training data/model, fonts, icons and licensed formatter assets |
| `tests/` | Controlled functional and regression coverage |
| `scripts/` | Setup, training, evaluation, asset preparation and Windows packaging |
| `evaluation/` | Methodology, capability notes, pinned public labels/snapshots and portable verification summary |
| `design/` | Design notes and future architecture/LLD module proposal |

## Limits and trust

Analysis parses source without importing repository modules. It reports **potential impact**, not proof of failure or coverage. A passing syntax/signature check does not establish behavioral equivalence. Model proposals may be rejected or legitimately return no improvement. Structural rename/extract remains Python-only. The architecture review/LLD generation module is a future proposal, not an implemented feature.

See [USER_GUIDE.md](USER_GUIDE.md) for the detailed workflow and [LICENSE](LICENSE), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and bundled license files for attribution. Change Lens source is MIT licensed; third-party components retain their respective licenses.
