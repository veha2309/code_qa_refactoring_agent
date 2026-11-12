# Native 3D Lens and offline architecture/LLD

## Scope

The 3D Lens is a CPU-rendered perspective projection of bounded XYZ graph positions. It supports orbit, node dragging on a camera-facing plane, pan, zoom, reset, depth sorting, and the existing evidence drawer. It shares the existing 36-node graph, resolved/inferred edges and alternate evidence paths. It adds no dependency inference and no GPU/runtime requirement. Node positions are not persisted.

Architecture review uses the static index plus hash-checked Python AST import inspection. Local exact/relative Python imports are resolved only when the target is unique; import conditions are not executed or evaluated. The implementation LLD includes declaration ownership, locations, Python signatures/bases/assigned fields, foreign declaration excerpts, and recorded relationships. Runtime types, services, databases, framework wiring and intended requirements are not reconstructed.

Findings explain resolved dependency SCCs, definitions spanning at least 80 source lines and files referencing at least five distinct local files. These are disclosed review heuristics. Inferred-only cycles are not promoted to resolved cycles. Missing links are not evidence of independence.

## Exports and bounds

Exports are unique folders with report.json, report.md, architecture.svg and lld.svg. Current revision and file hashes are checked before writing; saved-source snapshots and limits remain in the report. No target modules or tests execute. SVG uses escaped source text, bounded diagrams (48 nodes / 160 visible-node edges) and no external resources. UI previews are bounded; complete inventories remain in exports. Python fields/bases are declaration-level facts, not proven runtime types.

## Verification

178 automated tests cover existing workflows plus LLD fields/signatures, import-only/relative/ambiguous module cases, evidence cycles, separation of inferred edges, iterative large-graph SCC handling, cancellation, Unicode paths, export freshness/escaping, SVG parsing, native perspective projection/orbit/reset and shared evidence selection. Existing Rope deprecation warnings remain.

Controlled source and frozen checks use --self-test-architecture and verify 3D evidence, native orbit/reset, LLD/cycle findings, standalone exports and stale-export rejection. Diagrams and UI are visually inspected. No speed claim is made for the presentation laptop. No external repository code or actual LLM was executed for these checks.

## Reproduce

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:CHANGELENS_TEST_NO_AI = '1'
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe launcher.py --self-test-architecture .runtime/architecture_source.json
powershell -ExecutionPolicy Bypass -File scripts/build.ps1 -OutputDirectory dist/architecture
```

Use an isolated LOCALAPPDATA directory outside a Git repository for controlled smoke projects. The latest bundle is dist/architecture/ChangeLens; distribute the complete folder.
