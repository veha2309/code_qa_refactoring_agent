# Installed Ollama integration — 2026-10-29

The app now discovers already installed Ollama models on startup when no explicit disabled preference is saved. This is a read-only local model-list request: it neither downloads a model nor loads one into GPU memory. The existing explicit disabled preference remains respected. An explicit review/refactor action can reconnect on demand and continues automatically when the assistant model is detected, provided the workspace, buffer and selection have not changed.

Assistant availability no longer depends on loading the autocomplete model first. `qwen2.5-coder:3b` supplies explanations, focused/project-sample findings and reviewed refactoring proposals. `qwen2.5-coder:1.5b-base` supplies completion when installed. Existing one-model-at-a-time activation remains in place. A connection failure reports the actual failure rather than claiming Ollama is not installed.

Notes displays the current source language and model capabilities. Refactor has an optional goal field, such as simplifying conditionals. The goal is passed to the local model while existing signature, syntax, import/dependency, snapshot and explicit-application checks remain enforced. A model response with no change remains a legitimate no-preview state; no artificial patch is fabricated.

Model findings and reviewed rewrites are supported for indexed Python, JavaScript/JSX, TypeScript/TSX, Dart/Flutter, Java, C#, Go and Rust declarations. Structural rename/extract still uses the Python-specific engine and is labeled separately. These are different capabilities; detecting the installed model does not supply semantic rename engines for arbitrary languages.

## Live native UI verification

```
.venv\Scripts\python.exe launcher.py --self-test-ollama-languages .runtime\ollama-live.json
```

The check uses a disposable project and the real installed model, not a stub. Its first model action starts disconnected, discovers the prepared models, and resumes without another click. It reviews JavaScript, TSX and Dart, then asks for conditional-return simplification and validates each generated preview. The controlled source files remain unchanged and none of their code or tests is executed.

The source UI run passed all six live findings/proposal checks using `qwen2.5-coder:3b`. Findings took 0.52–1.02 seconds and previews 0.42–0.53 seconds in that warmed-model run. These are small controlled examples, not project-scale latency guarantees. One Dart uncertainty statement incorrectly implied zero/negative inputs were unhandled despite the else branch; model findings remain interpretation requiring source review. Syntax-valid proposals are not evidence of preserved behavior.

Regression coverage includes assistant-only installation without completion-model loading, deferred TypeScript findings, default startup discovery, explicit opt-out, nine-language UI/context/preview checks, project findings, stale context protection, and existing apply/revert safeguards.

Final verification: **263 tests passed across 19 isolated test files**. The `dist/ollama-integrated/ChangeLens` executable passed all six live Ollama findings/rewrite checks for JS, TSX and Dart, plus both standard native architecture and editor/focus workflows. Packaged live findings took 0.50–2.55 seconds and previews 0.44–0.53 seconds in that run. Embedded integration modules were checked against source. Reproduce the packaged live check with `ChangeLens.exe --self-test-ollama-languages OUTPUT.json`; it requires the already installed local coding models and performs no downloads.
