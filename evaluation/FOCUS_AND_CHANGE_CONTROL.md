# Focused workspace, change recovery and model context

The persistent app header, menu bar and workspace strip are collapsed into Options. Page tools and the design inspector appear on request. The primary Lens is the readable 2D trace; experimental spatial mode is available through Options. Component search ranks exact names and preserves real graph evidence.

Editor markers use Git HEAD or the saved project comparison, including changes that existed when the file opened. The review dialog previews line hunks, supports one-step undoable buffer reverts, and separately exposes last-save/opening comparisons and saved history. File history records successful Change Lens saves and restorations; compatible older refactoring backups are included. Restoring requires the expected current digest, preserves saved raw bytes and records a new recovery point. Git's index and commits are unchanged. Historical external-tool edits are not recoverable unless separately recorded.

The fixed 3,500-character model cap is replaced by conservative UTF-8-based token estimates, output reservations and model-capacity checks. Assistant requests select a fitting 2K/4K window (4K default maximum), with optional 8K. Token estimates are not an exact tokenizer. Large rewrites use exact old/new snippet edits on a disclosed cursor-centred excerpt; omitted source is preserved locally. Python and foreign-language proposals still pass full-source syntax/signature/import checks before preview. Completed responses disclose context coverage; truncated responses and detected budget overruns are rejected. Complete understanding of omitted source is not claimed.

## Verification

193 tests cover the existing workflows plus file history/restoration/conflicts, BOM/CRLF and Unicode paths, older backup recovery, undoable/stale hunk handling, baseline markers including staged Git changes, component search, hidden-bar keyboard access, large Python/TypeScript snippet rewrites, preserved multiline literals and truncated responses. Completion-popup newline insertion is deferred until native popup-event dispatch finishes, avoiding a reentrant text mutation caught during verification.

The controlled source/frozen --self-test-focus exercises the compact UI, graph search, edit markers, hunk revert/undo, saved restoration and context guards with a stub model. The frozen architecture check continues to cover the design editor. Read-only native previews use the supplied 3d-mapper project; its modules and tests are not executed.

A live local qwen2.5-coder:3b check supplied a 17,379-character synthetic function. It selected an excerpt covering declaration lines 211–225, reserved 768 output tokens inside a 2K window, reported 346 actual input tokens, returned result += value as an exact edit, and preserved the omitted prefix. This is one correctness example on the development machine, not a target-device performance/quality benchmark. The prior sandbox-only connection attempt was unavailable; the normal local runtime check passed.

Latest folder bundle: dist/focus/ChangeLens. Keep the whole folder together. No external model API, source execution, cloud fallback or model-weight download was used for these checks.
