# Multi-language expansion

This release extends the native Lens workflow without executing project code during indexing. Tree-sitter grammars are bundled; opening these languages needs no language server, compiler, internet, cloud account or Node installation.

| Language | Static analysis | Test execution | Reviewed refactoring |
| --- | --- | --- | --- |
| Python | Existing AST calls, aliases, fixtures and labeled inferences | Selected pytest tests, after trust | Existing Rope rename/extract and checked local AI proposals |
| JavaScript / JSX | Functions, classes, imports/exports, CommonJS, lexical calls and JSX references | Existing Node runner or installed Jest/Vitest; files/filters, after trust | Unavailable |
| TypeScript / TSX | Same reference analysis, plus local tsconfig/jsconfig path aliases | Installed Jest/Vitest with project TypeScript setup; files/filters, after trust | Unavailable |
| Java, C#, Go, Rust | Declarations, named tests and conservative module/package relationships | Recommendations only | Unavailable |

Selecting a function in a structural adapter traces its containing file/module and reports that widening explicitly. Shared Go packages and Java/C# namespaces create inferred, broad relationships; they are not resolved method calls. File edits may recommend unrelated tests in the same package. Rust handling covers straightforward local `mod` and `crate::` file links, not the complete crate/module/type system.

## Framework detection is a separate capability

Manifest declarations identify React, Next.js, Express, NestJS, Angular, Vue, Svelte, Vitest, Jest, Django, Flask, FastAPI, Spring Boot (Maven), ASP.NET Core, Gin, Echo, Axum and Actix Web. The UI and exported report retain the declaration path and evidence. Detection does not establish complete framework support.

JS/TS files within React, Next.js and Node projects use the language reference adapter. Framework routing, middleware registration, dependency injection, reflection, virtual dispatch and runtime wiring are not resolved. Angular HTML templates, Vue `.vue` and Svelte `.svelte` components are not parsed. Unsupported component formats produce a warning when their framework dependency is declared. No PHP, Ruby, C/C++, Kotlin, Swift, HTML-template or cross-language FFI analysis is provided.

## Deliberate boundaries

- Lexical JS/TS resolution supports straightforward relative imports, named/default exports, namespace imports, re-exports, CommonJS identifier exports and local JSONC path aliases. Ambiguous files, external/dynamic calls, shadowed references and unresolved receivers remain unresolved. Callback references and `this` method matches are labeled inferences.
- This is syntax/reference analysis, not a TypeScript type checker or complete Node/bundler module resolver. tsconfig `extends`, workspace package exports, conditional exports, declaration merging and framework-generated imports are not modeled. Type-only imports are omitted from runtime reference bindings.
- Literal `test`/`it` callbacks are discovered statically in test/spec files or through explicit supported test-library imports. Dynamically generated test names and parameterized cases are incomplete. Test registration does not prove a framework can collect/run that file.
- JS/TS test selection runs **files or path filters**, not individual discovered callbacks. Node and Jest run all tests in selected files; Vitest filters can match additional files. Runtime configuration and plugins may run project code after trust. The app never installs dependencies, runs npm scripts, starts the application or executes tests on folder open.
- Local coding model completion and focused explanations accept the active supported language. No per-language quality benchmark has been performed. Static Jedi completion/F12 navigation and structural rename/extract remain Python-only. The later workflow release adds checked AI proposals across indexed languages; see WORKFLOW_REFINEMENTS.md.
- Non-Python recommendations use structural ranking. The experimental learned ranker is trained on Python synthetic examples and is not applied to these languages.
- Snapshots and first-open comparisons include supported source files and recognized manifests. Configuration edits widen impact conservatively. Existing Python-only saved baselines migrate without treating unknown old JS/TS state as a change.

## Reproduce verification

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:LOCALAPPDATA=Join-Path (Get-Location) '.runtime'
.\.venv\Scripts\python.exe -m pytest tests -q --basetemp .runtime/language-tests
.\.venv\Scripts\python.exe launcher.py --self-test-languages evaluation/source_smoke_polyglot.json
```

The controlled tests cover JS/TS import aliases, re-exports, CommonJS, JSX, lexical shadowing, ambiguous modules, cycles, Unicode paths, syntax errors, deleted exports, staged/untracked changes, baseline migration, configuration edits, static framework detection, all bundled grammars, native editor guards and stale results. A real Node test fixture is checked for both pass and deliberate failure when Node is installed. Jest/Vitest command construction is checked with inert fixture entrypoints; full Jest/Vitest runtime integration and public-repository accuracy have not been benchmarked.

The packaged `--self-test-languages <report.json>` verifies every bundled grammar, the native JavaScript → TSX/test evidence workflow, automatic comparison, a paired diff and deliberate Node test failure (if Node is installed). Machine-readable results are stored in `source_smoke_polyglot.json` and `packaged_smoke_polyglot.json`.

These are controlled functional checks, not new public-repository Recall@5, ranking quality or performance results. Earlier public-repository evaluations remain Python-only. The architecture review / LLD generation proposal is still a separate future module.

## Verified release results

- Full automated suite: **122 passed**, with 12 pre-existing Rope deprecation warnings. Output: `polyglot_pytest.txt`.
- Source and frozen Windows language smoke: **11 checks passed** each, including every bundled grammar, JS/TSX evidence, refactoring guard, saved comparison/diff and deliberate Node failure. Reports: `source_smoke_polyglot.json`, `packaged_smoke_polyglot.json`.
- Frozen Python smoke: **passed through stage 6**, covering analysis, rename preview, successful demo tests, controlled failing-demo recall, training and static completion. Report: `packaged_smoke_polyglot_python.json`.
- Frozen local AI smoke: **passed through stage 13**, including actual inline completion, checked Python rewrite preview and focused impact brief. Report: `packaged_smoke_polyglot_ai.json`.
- One controlled TypeScript local-model completion produced `a + b;` and passed the bundled syntax parser. The TypeScript brief returned valid structured content. Generated code was not executed. Report: `multi_language_ai.json`. This does not establish broad language quality or speed on the presentation laptop.

Release executable: `dist/polyglot/ChangeLens/ChangeLens.exe`. Preserve its complete folder. The new grammar distributions and their licenses are included in the bundle.

The later workflow release adds Dart/Flutter and reviewed AI generation/regeneration across languages. See [WORKFLOW_REFINEMENTS.md](WORKFLOW_REFINEMENTS.md) for current capabilities and limits.
