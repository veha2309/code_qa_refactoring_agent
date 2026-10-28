# Local proposal response repair — 2026-10-28

The refactor workflow previously asked Ollama for arbitrary JSON. A JSON object without a string `code` field then failed at patch generation with “The model must return a JSON code proposal.” The Refactor page could remain on its preparation message after this failure.

Rewrite requests now send an explicit JSON schema. Small declarations require string `code` and `explanation`; large declarations require 1–6 exact snippet edits and an explanation. Local validation rejects missing fields, wrong types, empty code and extra keys. Only a single enclosing JSON fence is normalized; prose is never guessed into executable source.

Invalid format receives one corrective regeneration using the same bounded source and schema. The malformed response is not copied into the next prompt. Schema overhead and retry instructions are reserved in context budgeting. Cancellation, actual prompt usage and truncation checks remain active. Syntax, public signature, dependencies, freshness and explicit review checks remain unchanged.

Failure clears the preparation state and patch preview. Source files remain unchanged and Apply is unavailable.

Verification:

- Full automated suite: 201 passed, 12 existing Rope deprecation warnings.
- Regression cases cover malformed JSON, missing/wrong fields, empty code, prose, bounded retry, a valid fenced object and the Refactor error state.
- Installed local `qwen2.5-coder:3b`: a synthetic JavaScript temporary-variable rewrite returned valid schema-conforming JSON on its first attempt, in 2.08 seconds on this development machine. It used a 2,048-token window. This is not a general accuracy or performance benchmark.
- No external repository code was executed for these checks.
