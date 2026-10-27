# Lens: change investigation as the primary interface

This design centers Change Lens on its analysis rather than replicating a general IDE. The main native canvas shows focus → affected code → test evidence. Selection highlights the recorded path and dims unrelated nodes. Evidence opens on demand; files stay behind a toggle during investigation. Editor, diffs, tests and reviewed fixes remain available.

Clean repositories open in clearly labeled function exploration. Saved changes refresh automatically. The map uses indexed edges and historical records, never model-invented links. A focused map is recomputed per root so shared callers are not lost when the underlying report contains several changed symbols. Up to 36 nodes are displayed, with an explicit omitted count; detailed evidence remains available. Test actions select the focused path's linked tests, including tests beyond the displayed node cap.

The Brief view uses a bounded reading column and rendered Markdown. Model setup is collapsed and model interpretation is identified separately from recorded evidence. Explanations focus on a selected function, fragment or evidence path rather than dumping a file summary. Briefs request structured output and bound the summary, uncertainty paragraph and three verification items individually, so a verbose model cannot fill the workspace with an unbounded response. HTML, resource/image loading and link navigation are disabled in model output.

Regression coverage: `tests/test_lens.py` checks deterministic root filtering, map bounds, actual node clicks, source navigation, on-demand details, Markdown behavior, shared callers across multiple changed roots, and focused test selection. Existing editor, automatic comparison, static analysis, completion and refactoring suites remain in place.

This is a usability and product-identity change, not evidence of superiority over other tools. It preserves the 16 GB RAM / 4 GB GPU local-model preset. Graph rendering is native Qt with a bounded item count; no browser or new GPU model dependency is introduced.
