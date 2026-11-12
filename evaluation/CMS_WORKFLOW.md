# CMS exploration and change review — 2026-10-29

This release connects saved-code change review to source-backed React/Express feature journeys. It remains an offline static analysis tool; endpoint candidates, model explanations and registered middleware do not establish runtime behavior.

## Workflow

Use **Explore a feature** in Lens, then search by application, screen, endpoint, helper or file. Requests are sorted by application and screen. System overview, feature selection and Implementation detail have breadcrumbs and Back/Forward. Implementation detail exposes relationship classifications and exact source witnesses; activating a witness opens code. Existing editable cards, group dragging, Undo/Redo and exports remain available. 3D world coordinates remain fixed.

Named ES-module re-exports and explicitly bound request wrappers are followed. A single direct return or member-access return can carry a request result into a caller's direct state setter and list rendering. Computed/transformed returns, multiple returns, ambiguous bindings, cycles and expansion limits remain gaps. Recursive local controller/service helpers expose their model operations and source relationships; arbitrary argument substitution, control-flow execution and interprocedural data-flow proofs are not implemented.

Changed or potentially affected symbol ranges join to journey source witnesses. The Lens feature selector opens the corresponding implementation evidence. Changes retain their original impact paths in report JSON. Related local-AI context now contains labeled, budgeted source excerpts, types, linked tests and available fresh feature context, plus omission information. Rewrite proposals retain syntax/signature validation, explicit preview/application and recoverable history. Live-model quality was not benchmarked.

Diagram annotations persist in the current user's application-data directory in `feature-drafts.sqlite3`, isolated by workspace identity. Refresh rebases property edits over extracted source facts; altered or missing facts retain review-required overlay records. Reset to source clears stored annotations. Existing v1 design files remain readable through the current validated loader. Flow report version 2 adds snapshot identity, stable feature identifiers, typed steps/relationships, service chains and gaps while retaining existing fields.

Module facts use a bounded process-local cache keyed by extractor version, relative path and source hash. Current file-set imports and model targets are rejoined on every analysis, including deletions. The cache is warm within one app session; a restart performs cold extraction. Repository-switch epochs discard older worker results, and cancellation keeps the last usable view.

## Reproducible checks

```
.venv\Scripts\python.exe -m pytest tests -q
.venv\Scripts\python.exe -m scripts.measure_cms PATH_TO_PROJECT --ui --output .runtime\cms-measurements.json
```

The project passed **246 tests**, with 12 existing Rope deprecation warnings, in 43.87 seconds. Added cases cover request re-exports, wrapper propagation and rejection, service helper cycles, typed witnesses, model/import deletion and restoration, stable identities after line insertion, annotation persistence/isolation/reset/rebase, navigation restoration, cancellation, rapid repository switching and controlled JavaScript proposal preview/apply/revert. Existing tests cover shared component consumers, route alternatives, stale proposals, unsaved buffers, editor boundaries and fixed 3D coordinates.

One intermediate run emitted a native Qt completion access violation. The isolated case passed, and the subsequent complete serial run passed cleanly. This remains an intermittent native-test stability observation, not a demonstrated CMS tracing failure.

The final `dist/cms/ChangeLens` Windows folder bundle passed both architecture and editor/focus smoke workflows. Checks include fixed 3D world coordinates, native group dragging, feature history/evidence, JSON/Markdown/SVG exports, stale export rejection, gutter edits, hunk revert/Undo, saved-history restoration and native completion Enter/Tab behavior. Large-context model checks use a stub. Embedded code objects for all twelve changed application modules were compared with the delivered source and matched; a fresh build directory was needed to avoid stale incremental bytecode. The inspector now scrolls to preserve usable controls beside the evidence table; 25 focused CMS/design tests passed after this layout adjustment.

## Read-only Calendar source review

The reviewed source was `backend-navigation`; no target code, tests, modules or API calls were executed. The scanner processed 1,464 modules with zero flow-parser exclusions and extracted 1,331 request sites: 965 unique method/path candidates, 29 ambiguous, 337 unlinked. These are extraction counts, not correctness scores.

Verified source chain:

- `cms/src/academic-cms/components/AcademicCalenderlist.js:14`: GET `/secured/academic/all-calendar/{id}?lang=all`.
- Explicit `/secured` and `/academic` router mounts lead to `getAllAcademicCalendar` in `controllers/cms/academicControllers/academicController.js:2272`.
- Line 2275 references `Calendar.find` with filter field `InstituteId` and the imported Calendar schema.
- Lines 2278 and 2281 contain alternative HTTP 200 (`status`, `data`) and HTTP 500 (`message`) responses.
- The client assigns `response.data.data` with `setCalendars` at line 15 and uses `calendars.map` at line 38.
- A separate DELETE request on the same screen is retained as a separate journey, with `Calendar.deleteOne` and its own response branches.

Configured origins, proxy routing, middleware authorization, selected branches and database/API outcomes were not verified.

## Timing on the available Windows computer

Measured on `IWAYPLUS-PC`, not the proposed presentation laptop. Analysis and UI timing used the real source tree; timings are observations from one run, not guarantees.

| Measurement | Result |
| --- | ---: |
| Repository indexing | 4.60 s |
| Cold flow extraction in worker | 28.08 s |
| Warm flow extraction in worker | 2.07 s |
| Warm cached modules | 1,464 |
| Feature view population | 85.73 ms |
| Five feature/navigation actions | 8.43–33.80 ms |
| Largest cold/warm worker event-pump interval | 153.24 ms |
| Largest additional warm-worker timer interval | 153.37 ms |

Measured feature navigation met the 100 ms target; measured view population and background event-loop intervals stayed below 500 ms. These checks cover the feature browser and flow worker, not every full-workbench operation. Presentation-machine verification is still required on that hardware. Full source indexing still runs on refresh; the new incremental cache accelerates flow extraction, not every analysis subsystem.

## Boundaries

CommonJS feature wiring, framework runtime injection, arbitrary promise transforms, computed routes and generalized cross-language functional flows remain unsupported. Python and Flutter retain their existing editor, structural analysis and proposal support. Large diagrams retain bounded previews and complete structured evidence. The feature evidence table and JSON/Markdown expose additional details beyond preview limits.
