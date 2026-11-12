# Design panning repair — 2026-10-29

The shared Design canvas previously used rubber-band selection for background dragging and a tightly bounded scene rectangle. Space temporarily changed Qt's drag mode, which made navigation difficult to discover and limited movement when the diagram fit the viewport.

The canvas now handles navigation explicitly, with a view-only navigation extent that grows as needed. It does not modify diagram coordinates or exports. This applies to the Code structure canvas and the System & feature flows canvas, including both HLD and LLD.

- Drag background: pan.
- Middle drag or Space+left drag: pan anywhere, including over selected cards.
- Pan toolbar toggle: use left-drag over cards for navigation; toggle off for card editing.
- Shift+background drag: rubber-band selection.
- Wheel/trackpad: scroll; Shift+wheel: horizontal scrolling.
- Ctrl+wheel: zoom around the pointer.

Focus loss clears temporary hand/drag state. Card selection, multi-card movement, Undo/Redo and fixed Lens 3D coordinates remain separate from canvas navigation.

Verification: **249 tests passed**, with 12 existing Rope deprecation warnings, in 35.83 seconds. Added tests exercise repeated background drags beyond the original bounds in HLD and LLD, middle/Space/tool panning over cards, unchanged model positions and Undo history, Shift box selection, trackpad scrolling, horizontal wheel scrolling, pointer-anchored zoom and focus reset. Existing card/group drag tests passed. The packaged architecture smoke also checks viewport movement over cards without moving their coordinates or recording an Undo command.

Windows folder bundle: `dist/panning/ChangeLens`. Keep the entire folder together.
