# Change Lens workbench

Change Lens is a native Windows workspace for investigating changes across supported languages. Its main experience is the Lens: an interactive map of focused code, potential impact and test evidence. Editing, diffs, local completion and structural refactoring support the investigation.

## Start

The latest executable is `dist\workflow\ChangeLens\ChangeLens.exe`; older builds remain in `dist\automatic`, `dist\refined` and `dist\ChangeLens`. Keep the whole ChangeLens folder together. The build is unsigned and has no installer. Standard source builds through `scripts\build.ps1` write to `dist\ChangeLens`.

For development, run `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1`, then double-click `Start Change Lens.cmd` or run `.\.venv\Scripts\python.exe launcher.py`. Setup downloads free dependencies; normal editing, completion, refactoring and analysis run offline.

## Everyday workflow

1. **Open a folder.** Indexing and comparison setup happen automatically. Git projects use their latest commit. Other folders get a comparison point on their first open, preserved across sessions. Edits made before that first recording cannot be recovered.
2. **Edit and save.** Checks refresh after a short pause without switching away from your code. Detected external file changes refresh checks too; clean open buffers reload, while unsaved buffers are preserved.
3. **Follow changes.** The Lens shows paths from a focused change to affected code and tests. Click a node to highlight its path and open the evidence drawer. **Read diffs** opens saved edits; **Run linked tests** selects tests for the focused path. Test execution still requires an explicit action and initial repository trust.

With no recorded edits, the Lens automatically explores a function and clearly labels that state. The function picker changes focus without another setup step. **Fit map** fits the graph; drag to pan, scroll to explore and Ctrl+wheel to zoom. Large maps show at most 36 nodes and disclose the omitted count. The complete impact table remains under **Evidence table**. Solid links are resolved static references; dashed links contain inferred or historical references. Neither establishes that a test will fail.

The file panel is hidden in Lens and Brief. **Files** or Ctrl+B toggles it; **Editor** or Ctrl+1 returns to code. Node **Open this code** opens the corresponding source. Details remain hidden until a node is selected. **Explain this path** opens a focused model brief based on the displayed symbols and source lines.

Comparison selection and run settings remain under **Advanced** options. They are not required for ordinary use. Automatic checks do not save unsaved buffers or execute repository code. **Follow changes**, refactoring previews and test runs save editor buffers as explicit workflow actions.

## Language and framework support

Python retains its existing call/fixture analysis and reviewed refactorings. JavaScript/JSX and TypeScript/TSX now support lexical calls, local imports/exports, CommonJS identifiers, re-exports, JSX component references and local tsconfig/jsconfig aliases. Java, C#, Go and Rust provide declarations and conservative file/module/package relationships; selecting one of their functions traces its containing module and discloses that widening.

Framework dependencies are detected from manifests and shown with their source. React/Next.js/Node scripts use the JS/TS adapter; routing, DI, templates and dynamic framework wiring remain incomplete. Vue/Svelte component files are not parsed. See the full [capability matrix and boundaries](evaluation/MULTILANGUAGE.md).

Use Ctrl+Shift+P → **Project: Open web sample** for an editable React/TSX + JavaScript example. Existing sample edits are preserved. Its dependency-free test file runs with an already installed Node.js 20+; React itself is only a static example and is not launched or installed.

JS/TS tests run through Node or an already installed Jest/Vitest after repository trust. **All tests in selected files may run**; Vitest path filters may also match additional files. The app does not install dependencies or invoke npm scripts. Select tests from one package and one execution family at a time. Other new languages offer recommendations only. Static framework declarations do not guarantee test tool availability.

Inline local AI completion and focused explanations accept these source languages. Jedi completion/F12 and structural rename/extract remain Python-only. Reviewed AI rewrites now support all indexed source languages, including Dart. Non-Python tests use structural ranking because the learned starter model has only Python training examples.

## Local coding AI for the presentation laptop

The preset targets **16 GB RAM and an RTX 3050 with 4 GB VRAM**. It uses `qwen2.5-coder:1.5b-base` for inline completion and optional `qwen2.5-coder:3b` for explanations and suggested rewrites. Both requests use a 2,048-token context; the app unloads its previous model when switching between them. Actual speed and memory headroom must be tested on the presentation laptop, especially when other GPU applications are open.

Install and start [Ollama for Windows](https://ollama.com/download/windows) once. Open **Brief → Model settings**, prepare the autocomplete model (about 1 GB), and optionally the brief model (about 2 GB). **Connect models** checks and warms downloaded models. Settings collapse once the brief model is ready. Setup is remembered for later launches. Downloads require internet; normal inference uses only `127.0.0.1:11434`, with proxies bypassed and cloud models rejected. The executable does not include Ollama or model weights; prepare the presentation machine before disconnecting from the internet.

After pausing at the end of a line, generated code appears in muted text. **Tab** accepts it as one undoable edit; **Escape** dismisses it; **Ctrl+Enter** requests a completion. **Ctrl+Space** remains Jedi name/attribute completion. Suggestions are discarded if you change the source or cursor before the response arrives. Model loading can make the first request much slower than warm requests; loading happens in a background worker.

In **Brief**, use **Explain focused code** or **Propose a reviewable improvement**. Unfocused whole-file summaries are avoided; choose a function or a selected fragment. Markdown is rendered as readable text, with HTML, image/resource loading and link navigation disabled. Model interpretation remains separate from recorded evidence. A generated rewrite must preserve the function signature and decorators, pass syntax validation, and contain no new imports. It opens as a diff and only writes source after **Apply reviewed patch**, with the existing backup and freshness checks. These checks do not establish semantic equivalence. The assistant handles functions/fragments up to 3,500 characters; it is not an autonomous repository-wide editing agent.

On the actual presentation laptop, click **Brief → Model settings → Check presentation readiness**. This measures three completions locally without executing generated code and saves a report under application data. No development tools are needed for this check. A command is also available for source development:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_local_ai --output evaluation\presentation_laptop.json
```

The existing scratch-trained logistic model still ranks tests. The optional coding LLMs are pretrained models, not models trained from scratch by this project.

## Editor details

1. Choose **File → Open folder** (**Ctrl+O**) for your own repository, or **Open sample project** for an editable copy under `%LOCALAPPDATA%\ChangeLens\sample-project`. Existing sample edits are preserved.
2. Use the file explorer to open files or select a function. Tabs show an unsaved marker when modified.
3. Press **Ctrl+Space** for local Python completions. Suggestions also appear after a dot or an identifier prefix. Enter/Tab accepts the selected item. Completion is static Python intelligence from Jedi, not LLM text generation.
4. For Python, press **F12** to follow a resolvable definition within the workspace. Right-click the editor for completion and refactoring commands.
5. Press **Ctrl+S** to save. Saves preserve the file's encoding and newline convention and reject conflicts with edits made outside the app. **Ctrl+F** opens file search.

The editor supports Python, JS/JSX, TS/TSX, Java, C#, Go, Rust, Dart and common text/config files up to 2 MB. The analysis engine supports Python syntax understood by the bundled Python 3.10 runtime; unsupported syntax is reported.

**Ctrl+P** searches project files. **Ctrl+Shift+P** opens the searchable command palette; use Up/Down and Enter to choose a command. **Ctrl+B** toggles the file panel. **Ctrl+Shift+O** opens the optional outline. The bottom strip opens Lens, Editor, Diff, Tests, Fix and Brief. The evidence table and diagnostics remain in the View menu and command palette. **Ctrl+1** returns to the editor with open files and cursor positions preserved.

## Format a document

Use **Format** in the editor header, **Alt+Shift+F**, **Edit → Format document** or the command palette. Python uses bundled Black; JS/JSX, TS/TSX and JSON/JSONC use bundled Prettier and Node. No runtime installation or model is needed for formatting. Other languages currently have no formatter.

Review the paired diff, then **Apply to editor**. This is one undoable edit; **Ctrl+S** saves. Unsaved text can be formatted. Changed or closed buffers reject stale previews. Defaults use an 88-column target and two-space Prettier indentation. Project formatter configs/plugins are not loaded, and tests are not run. See [formatting and visual refinement](evaluation/FORMATTING_AND_GLASS.md) for limits and reproducibility.

## Review changes

Comparison setup is automatic. Both staged and unstaged Git edits are compared with HEAD; untracked supported source/configuration files appear as additions. Without Git HEAD, the first recorded comparison point is reused. **Diff → Advanced** allows choosing a comparison manually or deliberately replacing the recorded point; replacing it resets what counts as changed.

Explicit analysis saves dirty editor buffers before indexing. In **Diff**, select a file to read old and new code side by side. Removed lines and added lines use distinct backgrounds. Refactoring previews use the same paired viewer.

Snapshots preserve repository revision and SHA-256 file fingerprints. Analysis refreshes indexing before producing results. Excluded files include virtual environments, generated outputs, symlinks and files over 2 MB.

## Understand impact and tests

**Analyze symbol under cursor** in the command palette starts from the selected function or class. The optional outline also provides **Analyze symbol**. **Impact** shows a navigable relationship tree. Click a node for its code and the reason it was included; use **Open in editor** to return to its source.

Relationships include resolvable calls/import aliases, re-exports, transitive callers, pytest fixture injection, and explicitly labeled nested-scope and `self`/`cls` method inferences. Inferences are potential relationships, not runtime proof. Dynamic types, reflection, plugin fixtures, parametrization details and framework routing may remain incomplete.

Call resolution respects lexical imports, local assignments, parameters and enclosing function bindings. Calls inside lambdas and comprehensions remain explicitly unresolved. Fixture dependencies include statically named `autouse`, `usefixtures` markers on functions/classes/modules, imported fixture aliases, nearest overrides and literal indirect parametrization. Plugin-provided fixtures, inherited fixtures and dynamically constructed markers may remain unresolved; analysis never invokes pytest collection.

Symbol analysis uses the cursor location against freshly indexed source, so inserted lines do not silently select an old symbol. A cursor outside a function or class produces a placement message. Definition-time dependencies through decorators, default values and annotations remain incomplete.

**Tests** selects candidates with dependency paths rather than filling an arbitrary top-five list. Resolved paths rank before inferred paths; name-only and weak matches require manual selection through **Include name-only / weak matches**. Scores rank tests within their evidence groups and are not calibrated confidence values. The active model or structural fallback is shown above the list. Click a test for its full source-to-test evidence path, including filenames and line numbers. Manual selections survive filter changes until the next analysis.

Editing indexed source or configuration marks existing results and previews out of date. Saving refreshes checks automatically; typing a refactoring name refreshes its preview. Source hash checks also reject disk changes before execution or patch application. Native filesystem monitoring observes indexed files and up to 2,048 non-excluded directories. Use **Follow changes** after unobserved changes, including Git metadata outside the opened folder in some worktrees. JSON and Markdown reports distinguish recommended tests, unlinked candidates, actual selected-test outcomes and checks not performed.

No resolved test path is a possible linkage gap, not proof that coverage is absent. Module-level edits conservatively include symbols in the affected Python file.

## Run tests

The bundled integrity-checked template has a fixed controlled test workflow. The editable sample and your own projects use a detected Python interpreter with pytest and the project's dependencies installed. **Advanced run options → Browse** selects another interpreter when detection is insufficient.

For your own project, click **Run selected tests** and explicitly trust the repository when prompted. Pytest imports and runs repository code, fixtures and plugins on your laptop. The app never does this just because you opened a folder. Trust is remembered only for the current app session and repository root.

Output is captured, cancellable and bounded by the selected timeout and a 2 MB log limit. On Windows, cancellation terminates the spawned process tree. Runs execute saved source, **not unapplied preview patches**. The separate **Demo fault check** is available only for the bundled controlled template and compares selected tests with the complete demo suite.

## Refactor

- **Rename:** place the cursor on a name and press F2. Enter the new name. Rope locates related references across Python files.
- **Extract helper:** select a coherent block of statements, right-click and choose Extract helper, then enter its name.
- **Extract variable:** select an expression, choose Extract variable and enter its name.

Rename previews refresh after you pause while entering a name. Extraction proposes an unused helper/variable name and starts a preview. **Preview changes** remains available for manual refresh. Syntax is checked for every proposed Python file. Uncertain dynamic usages can be missed; inspect the patch and run tests.

Extraction rejects names already bound in the selected or enclosing scope, and rename rejects detected collisions in its scope. These are conservative checks, not a guarantee that dynamic references are preserved.

**Export patch** leaves original files unchanged. **Apply reviewed patch** explicitly writes the reviewed changes after stale-snapshot and content checks. Original bytes are backed up under `%LOCALAPPDATA%\ChangeLens\backups\<id>` with a manifest. Non-Git projects get a baseline before their first applied patch if one does not already exist. If a write fails, the service attempts to restore already-written files; backup files remain available for recovery. Applying is not interruptible once writing begins.

The bundled template itself is read-only. Open its sample working copy to edit or apply refactorings. Save any new edits and create a fresh preview if the source changed after review.

## Models and evaluation

The experimental relevance ranker is logistic regression trained from scratch on 80 synthetic labeled pairs. It uses lexical/symbol/path overlap, module references and graph distance. It has no pretrained weights or embedding API. Jedi completion and Rope refactoring are independent of this ranker.

```powershell
.\.venv\Scripts\python.exe -m scripts.train
.\.venv\Scripts\python.exe -m scripts.evaluate
.\.venv\Scripts\python.exe -m scripts.demo_validation
.\.venv\Scripts\python.exe -m pytest -q
```

The 30 public evaluation cases use pinned Requests, Flask and Click source snapshots, ten function-selection cases per repository. Their annotated positive tests are partial and agent-reviewed. No public repository code is executed during this evaluation and the labels are not used in training. These are relevance experiments, not real-change regression results or a Copilot comparison. See `evaluation/RESULTS.md`, `public_labels.json` and `public_snapshots.json`.

```powershell
# Explicit online preparation only; downloads source without executing it.
.\.venv\Scripts\python.exe -m scripts.fetch_evaluation
.\.venv\Scripts\python.exe -m scripts.public_evaluate
.\.venv\Scripts\python.exe -m scripts.summarize
```

## Build and verify

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -OutputDirectory dist\lens
$env:QT_QPA_PLATFORM = 'offscreen'
.\dist\lens\ChangeLens\ChangeLens.exe --self-test evaluation\packaged_smoke.json
```

The executable self-test drives native indexing, evidence-based recommendations, Rope preview, demo validation, model retraining and Jedi completion. It writes a JSON result and window capture. Remove `QT_QPA_PLATFORM` from the environment for normal interactive use.

The build runner avoids injected document-runtime DLL directories so Qt uses the correct Windows ICU library. It includes a process-local workaround for CPython 3.10.0's disassembler issue and packages required dynamic-import metadata. No system Python files are edited. A newer Python patch release is preferable for future builds.

Qt remains dynamically linked. Noto Sans, Noto Sans Mono and Roboto Mono font licenses and dependency notices accompany the distribution. See `THIRD_PARTY_NOTICES.md`, `THIRD_PARTY_LICENSES` and `resources/fonts`.

SQLite source caches, baselines, sample working copies, model files and recovery backups are stored under `%LOCALAPPDATA%\ChangeLens`. These can contain repository source. Exports go to a chosen destination. Delete application data only when you no longer need its baselines or backups.

## Latest workflow refinements

See [WORKFLOW_REFINEMENTS.md](evaluation/WORKFLOW_REFINEMENTS.md) for the HydroNexus import repair, typing/indentation behavior, transitions and **View → Reduce motion**, file/project search, alternate impact paths, and multi-language reviewed AI generation/regeneration.

After edits, the Lens retains every project symbol in its focus picker and offers **All changes** for multiple changed symbols. Caller tracing still crosses files. **Ctrl+F** shows match counts and highlights; **Ctrl+Shift+F** searches project text with file/line results.

Dart/Flutter is supported for static declarations, widget-reference paths, tests, diffs and local AI. Use **Project: Open Flutter sample** in the command palette. SDK formatting uses an installed Dart SDK; Flutter test execution needs a prepared Flutter SDK and project dependencies, then explicit repository trust. The app does not download the SDK, resolve pub dependencies or launch an emulator.
