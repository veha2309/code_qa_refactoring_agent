# Change Lens native design

The current design centers change investigation: focus → affected code → test evidence. The Lens opens first, with a native interactive map and details revealed only on selection. Files are tucked away during investigation; the editor is one action away. The earlier Zed-inspired editor and Figma exploration are historical references, not the current design specification.

Use a restrained charcoal canvas, warm copper for focused source, slate/cyan for dependent code, and muted green for tests. Color is reinforced by explicit SOURCE / CODE / TEST labels. Dashed lines distinguish inferred or historical relationships. Selection highlights a path; it does not express probability. All graph relationships come from recorded analysis.

Keep the canvas dominant. Avoid repeated summaries, permanent setup controls, large metric cards, decorative animation and generic chat walls. Model briefs use a centered reading column with rendered Markdown and inert links/resources. The default flow is open → explore or edit → follow a path → inspect evidence → run linked tests or review a fix.

Implementation: `changelens/lens.py`, `brief.py`, `workbench.py`, `ai_workbench.py` and `theme.py`. Typography remains bundled Noto Sans with Roboto Mono for source. Native splitters, menus, keyboard navigation and ordinary Windows chrome remain available.

Earlier editable exploration: https://www.figma.com/design/mgVGrnsbpCSmI8q4JXIjYI (superseded).
