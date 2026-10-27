# Proposed offline architecture review and LLD module

This is the next module proposal, not an implemented feature or an assessment of a repository.

## First release

Build an **existing-design review** from local Python source, with a separate section for improvement proposals. Reuse the Lens evidence convention: every structural fact or finding carries source locations and a snapshot identifier. Preserve the 16 GB RAM / 4 GB GPU deployment profile and the existing offline/local-model boundary.

Outputs:

- A navigable module/package dependency diagram and cycle findings.
- Class-level LLD: classes, methods, signatures, annotations, attributes that can be statically identified, and resolvable inheritance/relationships.
- A bounded call-flow diagram for a selected function or entry point, with branches/inferences labeled. A static call-flow diagram must not be presented as an observed runtime sequence.
- A report explaining structure, findings, evidence, limitations, and separately labeled improvement proposals.

## Evidence model

Extend AST indexing with module import records, class bases, decorators, method signatures, annotations and ordinary `self.attribute` assignments. Resolve aliases and repository-local targets conservatively. Do not import modules, invoke framework startup, collect tests, evaluate decorators or execute repository code.

Record each entity and relationship with file/range, resolution kind, and source hash. Keep duplicate names qualified by module/class. Missing or ambiguous types remain unknown. Do not infer databases, services, deployment topology or architectural patterns solely from filenames or LLM assertions.

## Findings

Dependency cycles can be computed from the directed import graph. Coupling, size and complexity observations can use visible thresholds, but must be labeled heuristics rather than defects or an invented architecture score. Runtime plugins, reflection, dependency injection, framework wiring and inferred responsibilities must remain explicit limitations.

Use the local 3B model to explain one bounded finding or module at a time. The deterministic extractor supplies the facts. Model explanations are commentary, and proposed redesigns cannot silently replace the extracted current design.

## Export

Render diagrams from structured graph records using native/vector tools. Export SVG plus a self-contained HTML report with embedded diagrams, a Markdown report, and JSON evidence. No hosted diagram API, CDN, browser server, or cloud model is required. Include the Git revision, hashes, settings and unsupported areas. Stale exports should require refresh or clearly identify their old snapshot.

## Implementation sequence

1. Add the module/class graph schema and qualified AST extraction.
2. Add module dependency and class LLD views with source navigation and bounded diagrams.
3. Add deterministic findings and short evidence-grounded local explanations.
4. Add offline diagram/report exports and verification fixtures.

Verification should cover import aliases and relative imports, cycles, duplicate classes, inheritance, annotations with unresolved targets, syntax errors, dynamic wiring, Unicode paths, cancellation, large graph limits, and safe escaping of source names in SVG/HTML. Assert that analysis never executes repository code. Check exports against the structured graph; do not use model agreement as validation.
