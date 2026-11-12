# Change Lens

Change Lens is a native Windows workbench for tracing code changes, choosing relevant tests, and reviewing refactors. The Lens connects a selected function or saved edit to potentially affected code and tests. Each link carries source evidence you can inspect.

## Install and run from source

Use Windows x64, Git, and 64-bit Python 3.10 on your `PATH`. First-time setup needs internet access to install the pinned dependencies and prepare the bundled formatter and TypeScript refactoring assets.

```powershell
git clone https://github.com/veha2309/code_qa_refactoring_agent.git
cd code_qa_refactoring_agent
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
.\.venv\Scripts\python.exe launcher.py
```

After setup, you can also double-click **Start Change Lens.cmd**. Setup creates `.venv` and prepares the sample and its starter test-ranking model. Ordinary indexing, editing, and formatting run offline.

## First walkthrough

1. Press **Ctrl+Shift+P**, then choose **Project: Open sample**. This opens an editable copy of the invoice project. You can also click **Open** and choose your own project folder.
2. Open `invoice.py` and place the cursor inside `calculate_invoice_total`. In **Review**, choose **Review function**. Open **Lens** to follow the recorded impact paths and choose **Linked tests** to inspect the candidates.
3. In **Editor**, click `subtotal` to open the refactor panel. Enter a new name, preview the diff, then choose **Apply refactor**. The panel offers **Undo refactor** after a successful apply. Select an expression or block to preview an extraction.
4. Save an edit and choose **Review changes** to compare saved source against Git HEAD or the recorded first-open baseline. Use **Design** to inspect source structure and supported feature flows.

Run tests only in repositories you trust. Choose the project interpreter or test tooling before running the selected set. Test results are recorded separately from static recommendations.

## Language coverage

| Language | Analysis | Refactoring and test execution |
| --- | --- | --- |
| Python | AST references, aliases, callers, classes, and supported pytest fixtures | Rename and extract with Rope. Run selected pytest tests with the project interpreter. |
| JavaScript / JSX, TypeScript / TSX | Local imports and exports, CommonJS, lexical references, JSX, and supported config aliases | Rename and extract with the TypeScript language service. Run selected files or filters using a configured Node runner, Jest, or Vitest. |
| Dart / Flutter | Declarations, imports, constructors, widget references, and labeled build relationships | Run selected Flutter test files with a prepared SDK and project dependencies. |
| Java, C#, Go, Rust | Conservative file, module, and package relationships | Test recommendations. |

Optional model explanations and reviewed rewrite proposals are available across the indexed languages. Dependency links indicate potential impact. Dynamic dispatch, runtime routing, dependency injection, and other relationships can remain unresolved. See [analysis boundaries](evaluation/MULTILANGUAGE.md) and the [user guide](USER_GUIDE.md).

## Optional local coding models

Install Ollama separately and open **More → Local models / context settings**. The default preset uses `qwen2.5-coder:1.5b-base` for inline completion and `qwen2.5-coder:3b` for explanations and rewrite previews. Prepare each model you want to use, then connect it. Model downloads need internet access. Inference runs through the local Ollama service.

Use **More → Tools → Code notes** for focused explanations and model review. Change Lens can attach relevant saved definitions with file and line references. Review model suggestions and the proposed diff before applying. [Ollama integration and verification](evaluation/OLLAMA_INTEGRATION.md)

## Build a Windows bundle

Run setup once, then build from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build.ps1 -OutputDirectory dist/windows
```

Launch `dist/windows/ChangeLens/ChangeLens.exe`. To install a built copy, extract or copy the entire `ChangeLens` folder and launch the executable inside it. Keep `_internal` next to `ChangeLens.exe`. The bundle includes the app runtime and prepared assets. Ollama and project-specific test environments are separate.

If a source checkout is missing the formatter or refactoring engine, rerun `scripts/setup.ps1`. The build command uses the Windows icon and bundles the same app as the source launcher.

## Run the tests

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:CHANGELENS_TEST_NO_AI = '1'
$testDir = Join-Path ([IO.Path]::GetTempPath()) ('ChangeLens-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest tests -q --basetemp $testDir
```

The tests cover source indexing, review and impact workflows, model context, and preview, apply, and undo. Some checks need optional tools. The [evaluation directory](evaluation/README.md) describes the fixtures, smoke tests, and historical measurements.

## Repository layout

- `changelens/` contains the editor, source index, impact analysis, test runner, refactoring, and model integration.
- `resources/` contains the sample projects, app icon, fonts, and prepared asset locations.
- `scripts/` contains setup, build, training, and evaluation commands.
- `tests/` contains automated regression checks.

Change Lens is [MIT licensed](LICENSE). Third-party components retain their respective licenses. See [notices](THIRD_PARTY_NOTICES.md) and [bundled licenses](THIRD_PARTY_LICENSES/).
