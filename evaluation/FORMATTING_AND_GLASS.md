# Offline formatting and glass surface refinement

The updated native interface uses an ink palette, restrained sea-glass gradients, translucent surfaces, fine highlight borders, warm source-node accents and rounded navigation. Code backgrounds remain opaque for readability. The effects are drawn with Qt; no desktop capture, operating-system blur, web view, animation loop or GPU shader is required.

## Format a document

Open an editable document and use **Format** in the editor header, **Alt+Shift+F**, **Edit → Format document**, the editor context menu or **Editor: Format document** in the command palette.

- Python: bundled **Black 26.5.1**, with its AST-equivalence/stability checks enabled.
- JavaScript, JSX, TypeScript, TSX, JSON and JSONC: bundled **Prettier 3.9.10**, using a bundled **Node.js 24.12.0** runtime. An installed Node or npm project is not needed for formatting.
- Other languages currently retain their earlier editing/analysis capabilities; this formatter does not support Java, C#, Go or Rust.

Formatting runs in a background worker against the current editor text, including unsaved edits. It opens a paired diff. **Apply to editor** creates a single undoable edit; **Ctrl+S** explicitly saves through the existing encoding/newline/conflict checks. Dismissing a preview leaves the source unchanged. Changed/closed documents and switched workspaces reject stale application. Already formatted documents receive a status message.

Defaults are an 88-column target, Python's Black defaults, and two-space Prettier indentation. Formatters do not read project formatter configuration, import repository modules, load project plugins, install dependencies, execute tests or contact a model. Node options and module-path environment injection are removed. Node formatting has a 15-second timeout and cooperative cancellation. Documents are limited to 2 MB. Formatters can change quote styles and wrap lines; always review the proposed diff. Formatting does not prove behavior preservation.

Recognized `tsconfig.json` / `jsconfig.json` files use JSONC so comments and trailing commas are accepted. This release does not provide format-on-save, selection formatting or configurable project style profiles.

## Reproducibility and verification

`requirements-lock.txt` pins Black and dependencies. `scripts/prepare_formatter.py` vendors Prettier from its pinned npm archive with SHA-512 verification and Node from the official fixed release with SHA-256 verification. The distribution includes both licenses, Node's embedded third-party notices and a file-hash manifest under `resources/formatting`. Normal application formatting works offline; preparing missing build assets requires an initial network connection.

```powershell
.\.venv\Scripts\python.exe -m scripts.prepare_formatter
$env:QT_QPA_PLATFORM='offscreen'
$env:LOCALAPPDATA=Join-Path (Get-Location) '.runtime'
.\.venv\Scripts\python.exe -m pytest tests -q --basetemp .runtime/formatter-verification
.\.venv\Scripts\python.exe launcher.py --self-test-format evaluation/source_smoke_format.json
```

The formatter tests cover Python AST equivalence, comment preservation, idempotence across all supported formatter parsers, invalid/unsupported/oversized input, cancellation, project config and Node environment isolation, native preview/application, buffer-only editing, one-step undo and stale previews. The frozen executable exposes the same `--self-test-format <report.json>` check to verify both bundled formatter engines and the native workflow.

The latest executable is `dist/glass/ChangeLens/ChangeLens.exe`. Keep the entire ChangeLens folder together.

## Verified release

- Full suite: **132 passed**; 12 existing Rope deprecation warnings. Output: `glass_pytest.txt`.
- Source and final frozen formatter smoke: **6 checks passed** each. Black/Prettier engines, idempotence, native preview, buffer-only application, single undo and stale-result rejection were verified. Reports: `source_smoke_format.json`, `packaged_smoke_format.json`.
- Final frozen language smoke: **11 checks passed**, including all bundled grammars, JS/TSX evidence, automatic comparison/diff and controlled Node test failure. Report: `packaged_smoke_glass_languages.json`.
- Final frozen core/local-AI smoke: **passed through stage 13**, including original Python analysis/refactoring, successful and deliberately failing demo tests, actual model autocomplete, checked Python rewrite preview and focused evidence brief. Report: `packaged_smoke_glass_ai.json`.
- Native screenshots were reviewed for the Lens, evidence drawer, paired diff, editor and formatter preview. Formatting requires no separately installed Node; project test execution retains its own runtime/dependency requirements.
