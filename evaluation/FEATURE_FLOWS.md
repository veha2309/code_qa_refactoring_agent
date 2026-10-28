# Source-backed feature flows and dependency layers — 2026-10-28

The declaration inventory is now separated from functional design. Design opens **System & feature flows** when supported HTTP requests are present. Search selects a client request; the implementation diagram includes source-backed route candidates, mounted prefixes/middleware names, handlers, input fields, model operations, alternative responses, direct result-to-state assignments and list rendering. Source references to request-wrapper functions are included when resolved by the existing index. Cards remain editable with Undo/Redo, design-file save/load, reset to source and SVG export. Ctrl+S and menu actions operate on the visible canvas.

The orbiting sphere projection has been replaced by fixed dependency layers containing labeled code cards. Drag pans, the wheel zooms and Home resets. Graph direction describes potential impact from a dependency to its callers. Broad inferred links are opt-in rather than mixed into the default resolved-reference graph. Node inspection retains both a witness path and direct references.

## Implemented extraction boundaries

- ES-module imports/exports and aliases, Axios instances created with `axios.create`, direct Axios calls and unshadowed global fetch syntax.
- Express application/router construction, literal routes, nested mounts, named imported handlers and inline handlers. Middleware after a router is not mistaken for the router. Unmounted routers are not assumed to be server entry points.
- Request-method and path-pattern compatibility, including parameter placeholders. Hosts and proxy configuration remain unverified; matches are explicitly candidates. Ambiguous candidates are retained rather than selecting a destination.
- Handler input field names, imported-model operation syntax/filter fields, conditions with operators/negation, helper-call names and alternative response statuses/shapes.
- Direct result-variable use by a React state setter after the request in the same lexical block, plus source references to that state in list rendering. Service indirection and other state mechanisms can remain unresolved.
- Application roles use package manifest evidence. Server outbound HTTP calls are not classified as frontend applications based on folder names.

CommonJS wiring, computed mounts/routes, framework-specific runtime injection, arbitrary service wrappers and other languages/frameworks are not functional-flow support. They retain code structure and explicit gaps. Nothing is executed to generate diagrams. Source/hash freshness checks apply to exports. Export adds systems.svg, flows.md and per-request SVGs; legacy declaration detail pages remain separate.

## Verification

The complete automated suite passed: 211 tests, with 12 existing Rope deprecation warnings. The final Windows folder bundle passed both the native architecture/flow workflow and editor/search/change-history/context checks. Model-context checks in the latter use a stub; no live-model accuracy claim is implied.

Controlled tests cover nested mounts with trailing error middleware, imported aliases, inline responses, model filters, success/error alternatives, direct UI propagation, comments, non-HTTP getters, client shadowing, dynamic URL prefixes, HTTP-method mismatch, ambiguous routes, unmounted routers, manifest roles, XML-valid SVG, nonoverlapping cards, feature search, editable draft Undo and diagram/report export. Existing regression tests cover impact aliases, duplicate names, cycles, alternative caller routes and stale snapshots.

Read-only check of the user's backend-navigation source: 1,409 JavaScript/TypeScript modules analyzed; 54 files skipped by the flow parser. 1,257 supported request sites were extracted, with 898 unique method/path candidates, 29 ambiguous and 330 unlinked. These are extraction counts, not correctness/coverage scores. The complete set has not been manually audited.

One real scenario was checked against source: CalendarList GET at cms/src/academic-cms/components/AcademicCalenderlist.js:14 → app.js:407 /secured mount → routes/securedRoutes.js:44 /academic mount → AcademicRoutesSecured.js:66 /all-calendar/:id → getAllAcademicCalendar at academicController.js:2272 → Calendar.find filtering InstituteId at line 2275 → alternative 200 status/data and 500 message responses → setCalendars(response.data.data) → calendars.map rendering. Configured host, middleware authorization, branch execution and API responses were not run or verified.

Native screenshots were inspected for the actual CMS Design view. No source changes or test execution were performed in the user's backend-navigation repository.
