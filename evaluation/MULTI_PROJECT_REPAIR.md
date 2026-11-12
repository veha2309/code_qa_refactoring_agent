# Multi-project Design and model workflow repair — 2026-10-29

The affected projects were Hydro Nexus and StockPulse. Both use Next.js; Hydro Nexus also contains FastAPI. The previous detailed HTTP extractor focused on Express, while the generic system view showed little for projects with no extracted client journeys. The Refactor UI also initially selected the Python structural rename operation in other languages.

## Behavior

- Design defaults to Pan mode: left-drag anywhere, including over cards, moves the viewport. Click a card for inspection. Turn Pan off to arrange cards; Shift-drag selects. Navigation resets to Pan when a new project/model is opened and does not change card coordinates, exports or Undo history.
- Every indexed language gets a module/dependency system overview. Directory grouping is structural, not an assertion about business responsibilities. Bounded previews expose complete indexed records in JSON; unsupported source languages/framework behavior remain explicit limitations.
- HTTP adapters now include Express, explicit Next.js App Router method exports, and direct single-module FastAPI/Flask application decorators. Next route groups and single dynamic segments are recognized. Catch-all/parallel routes, computed registrations, Python router/blueprint mounting and runtime framework injection are not resolved by the new adapters.
- Registered endpoints with no linked client are searchable standalone server entries with source-linked implementation details. They are not presented as proven client connections. Server-only projects have a useful Design view and JSON/Markdown/SVG export.
- Notes provides **Review focused code**. Design provides **Model findings** for a bounded sample of up to four source declarations; the result explicitly identifies sampled/omitted code. Both use the optional local model and label output as interpretation, not confirmed defects or execution evidence.
- Model findings, completion and syntax/signature-checked rewrite previews are available for Python, JavaScript/JSX, TypeScript/TSX, Dart/Flutter, Java, C#, Go and Rust. Non-Python Refactor views default to the model proposal operation; unsupported structural rename/extract choices are disabled. Structural cross-file rename/extract still uses the Python engine. Unsupported declaration shapes are rejected rather than applied unchecked.
- Ctrl+Space continues to use static completion for Python. In other indexed languages, an explicit request uses local AI when enabled, or explains how to enable it. Existing automatic local completion remains available.

## Read-only checks on the requested projects

| Project | Indexed files | HTTP requests | Registered routes | Unique method/path candidates | Standalone server entries |
| --- | ---: | ---: | ---: | ---: | ---: |
| Hydro Nexus | 99 | 2 | 6 | 0 | 6 |
| StockPulse | 75 | 8 | 32 | 6 | 28 |

Default left-drag panning was exercised over cards in both the Code structure and System overview canvases for each project. Viewport movement occurred without changing node positions or Undo history. Source repositories were not edited, imported, executed, or tested; verification settings/screenshots were isolated under this workspace's ignored runtime folder.

Hydro Nexus's client requests `/api/ingest`; the FastAPI app declares `/ingest`. Its inspected `next.config.ts` contains no rewrite. The connection remains unresolved: an external proxy/configuration could supply the missing prefix, and no runtime failure is asserted. A coastline JSON asset request also remains separate from backend route inference.

## Verification boundaries

Controlled tests cover Next.js parameterized endpoints and response shapes/statuses, explicit FastAPI/Flask registration, rejection of Next-style filenames without a Next manifest, server-only navigation, default panning on cards, and all nine language variants through focused findings, sampled-project findings and reviewed rewrite generation. These model tests use stub responses; they establish UI/context/validation behavior, not live-model accuracy.

The complete regression set is also run file-by-file in isolated Python processes. A monolithic run encountered the previously observed native Qt access violation while many test windows shared one QApplication; isolation avoids that accumulated test-window state and is reported separately from native packaged checks.

Final result: **261 tests passed across 19 isolated test files**, with no failed files. The Windows folder bundle at `dist/multi-project/ChangeLens` passed both native architecture and editor/focus workflows, including standalone Next route evidence and default navigation. Fourteen changed application modules in the executable were compared with source and matched. The fixed-coordinate Lens 3D and editable 2D group-movement checks still pass.

Correction: the initial loopback check ran inside the restricted sandbox and failed to reach the existing Ollama server. An unrestricted check confirmed Ollama running with both `qwen2.5-coder:3b` and `qwen2.5-coder:1.5b-base` installed. The app's actual LocalAI client then completed a live structured TypeScript review using the 3B model in 2.73 seconds on a 91-character example, with no omitted code and a valid summary/uncertainty/verification response. This confirms connectivity and the non-Python request path; it is not a broad model accuracy, rewrite-quality or GPU-memory benchmark. The nine-language regression workflows still use stub responses.

Detailed framework tracing is not universal across arbitrary frameworks or languages. The general source graph, usable navigation and local-model workflow are shared; framework adapters provide additional evidence only where supported.
