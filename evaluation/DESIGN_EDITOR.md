# HLD, LLD and native design editing refinement

The initial export selected 48 of 151 classes from the supplied 3d-mapper report, including generated platform code, and used a fixed grid with crossing connections. This release separates package HLD, scoped member LLD and editable draft designs.

## Verification on the supplied project

Read-only indexing of the supplied 3d-mapper source project retained 99 files, 151 class-like declarations and 993 symbols. Dart detail extraction found 537 method/function signatures, 749 declared fields and 37 enum values. Package grouping creates 15 production scopes containing 202 class/top-level-function records. Every eligible declaration is covered by the paginated diagram book; none are lost through a first-48 selection. Generated/test code is excluded only from diagrams by default. Target repository modules/tests were not executed or modified.

## Current behavior

HLD shows directory-based package components. LLD shows classes/functions, full available fields, operations, constructors and enums on the editor canvas. Extracted call/reference edges remain separate from unverified field-type name links. The canvas supports dragging, Space+drag pan, zoom, inspector edits, notes, proposed connectors, delete, current-page undo/redo, editable JSON save/load, automatic atomic draft recovery and SVG export. Current-page export is marked DESIGN DRAFT. Original source reports are not overwritten by manual proposals. Historical draft source navigation is disabled.

Source export creates package pages plus complete per-class/function detail SVGs, a linked index, Markdown and JSON. Editable page files and source report bundles are distinct artifacts. The native canvas is a focused diagram editor; it does not implement Figma collaboration, arbitrary vector drawing, live source-code synchronization or behavioral verification. Foreign languages other than Python/Dart may retain declaration excerpts without complete member types.

The 3D view now uses fitted perspective framing, distance planes, shaded nodes, readable test labels, collision-checked label boxes and selected/hover details. The same static graph and limits remain. It is a CPU renderer and has no target-laptop performance benchmark.

## Checks

184 automated tests pass, including Dart member extraction, diagram pagination/coverage, SVG parsing, label overlap, HLD/LLD editing, original-value retention, notes/connectors, undo/redo, recovery across navigation/restarts and source-isolation checks. The frozen architecture check also exercises canvas note editing, draft roundtrip and SVG export. Existing Rope deprecation warnings remain. A refresh race that could discard a patch during review was fixed and regression-covered.

Latest bundle: dist/design/ChangeLens. Distribute the whole folder. Source self-test: launcher.py --self-test-architecture <report.json>.
