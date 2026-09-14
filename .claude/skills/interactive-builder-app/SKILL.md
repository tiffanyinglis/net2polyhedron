---
name: interactive-builder-app
description: Details on `interactive_builder_app` (`src/apps/interactive_builder_app/app.py`) — a 2D shape-placement canvas for hand-building nets (palette, drag/rotate, edge connections, net JSON import/export), unrelated to solving or folding. Load before making non-trivial changes to this app.
---

See the `net-fold-project` skill for the untouchable-files list, directory
layout, and testing conventions shared across this whole repo — this file
covers only `interactive_builder_app` specifics. `reference/design-history.md`
in this skill's folder has the rejected-approach narratives behind the
choices below — read only when you need that reasoning.

## Interactive builder (`src/apps/interactive_builder_app/app.py`)

A 2D shape-placement canvas — unrelated to solving/folding, and to
`src/utils/` domain logic entirely. No test file (rest of `src/apps/`
stays untested by convention).

- **Palette**: one icon per regular polygon (triangle..8-gon), drawn from
  `polygon_geom.regular_polygon_vertices` at a shared CIRCUMRADIUS
  (`ICON_RADIUS`) — unlike a placed shape, which uses a shared EDGE
  length (`DEFAULT_SHAPE_EDGE_LENGTH`), matching every other net/mesh in
  this project. `POLYGON_COLORS` gives each polygon type one fixed color
  (never per-instance), from an explicit `_POLYGON_HLS` hue/lightness/
  saturation table (base 0.50/0.65 unless noted): triangle 136° green
  (0.38/0.50), square 172° turquoise (0.40/0.65), pentagon 208° blue
  (base), hexagon 244° blue (0.58/0.65), 7-gon 262° violet (base), 8-gon
  280° purple (base).
- **Pick up / drop**: clicking a palette icon arms that type
  (`self.armed_n`) and shows a ghost preview following the mouse, drawn
  exactly like a real selected shape (solid fill + selection outline).
  Clicking the same icon disarms; a different one swaps the armed type
  and deselects whatever's selected on canvas. Dropping places a real
  instance and disarms — it is NOT left selected afterward. Shapes live
  in `self.shapes`, a Z-ordered list (back to front); redraw iterates it
  front-to-back so a later drop renders on top.
- **Select / drag / delete**: `_on_canvas_press` hit-tests topmost-first
  (`_hit_test` via `_point_in_polygon` against current, possibly-rotated
  vertices) and selects or deselects. Dragging is not a separate code
  path — `_drag_state` records the press's world position and the
  shape's starting center; a click that never moves is a drag by zero.
  `self.selected_id` (at most one) draws in `SELECTION_OUTLINE_COLOR`
  ("red" — chosen because none of the palette's green/blue/purple hues
  are near it). `Delete` removes the selected shape AND any connections
  touching it (`_remove_shape`).
- **Edge connections** (`self.connections`): a connection stores
  `{"id","a_shape","a_edge","b_shape","b_edge"}` — an EDGE INDEX (position
  in that shape's vertex loop), not a coordinate, so it stays valid as
  either shape moves/rotates. `_shape_edge_midpoints` re-derives world
  midpoints fresh from current vertices every redraw, never cached.

  Every placed shape's every edge is a candidate handle regardless of
  selection — a handle draws as a solid filled dot (`HANDLE_COLOR`,
  white) if it's a real connection endpoint (always drawn), or an
  unfilled ring only when the cursor is within `HANDLE_HIT_RADIUS` of it
  (so a handle is never visible without also being clickable). Red
  (`lit`) overrides color/visibility for: every edge of the selected
  shape, the pending connection's own origin point, and its current hover
  target — never the whole hovered shape's outline, only that one edge.

  **Click-click, not click-drag.** First click on a handle
  (`_hit_test_any_edge_handle`, checked before ordinary shape/connection
  hit-testing since a handle can sit on top of a shape's body) arms
  `self._connection_pending` and clears `self.selected_id`. Motion
  (`_on_canvas_motion`) re-runs the same handle hit-test at the cursor
  (excluding the pending connection's own origin shape) to set
  `_hover_shape_id`/`_hover_edge_index` — this is proximity to a handle,
  not just being over a shape's body. The second click
  (`_complete_or_cancel_pending_connection`) does NOT re-hit-test its own
  position — it only reads whatever `_hover_shape_id`/`_hover_edge_index`
  already say, guaranteeing highlighting and completion are provably the
  same decision. A miss (`_hover_shape_id is None`) cancels without
  consuming the click, so it falls through to ordinary handle/shape
  checks — a click that cancels one pending connection can immediately
  arm a new one if it landed on some other handle.

  A connection line (`_draw_connection_line`, grey normally, red+thicker
  when highlighted) is hit-tested via perpendicular distance to the
  segment (not the infinite line). "Highlighted" means either it's
  `self.selected_connection_id` OR either of its own shapes is
  `self.selected_id` — selecting a shape highlights every connection
  touching it as a group.
- **Rotate / pan (right button, mutually exclusive)**: decided once at
  press time — ROTATE (trackball-style: each motion diffs the current
  screen-space cursor angle around the shape's center against the last
  event's angle, adding the delta to the shape's stored `rotation`) if a
  shape is selected, else PAN (`self.offset_x/y += drag delta` — dragging
  the background moves the view WITH the cursor).
- **Zoom**: scroll wheel zooms about the CURSOR — solve for the world
  point under the cursor at the old scale, re-derive the offset so it
  lands back under the cursor at the new scale.
- **Coordinates**: shapes are stored in world coordinates, independent of
  pan/zoom. `_world_to_screen`/`_screen_to_world` (one scale-plus-offset
  transform) are the only two conversion points.
- **Rendering**: plain `tk.Canvas` has no anti-aliasing — every polygon
  (placed shapes, ghost preview, palette icons) is rasterized through
  Pillow at 4x (`SUPERSAMPLE`) and LANCZOS-downsampled. `main()` also
  calls `_enable_windows_dpi_awareness()` (no-op off Windows), needed
  separately from anti-aliasing since Windows otherwise renders at a
  virtualized 96 DPI and bitmap-stretches to the real display scale. A
  placed shape is re-rasterized every redraw; a palette icon is
  rasterized once at build time.
- **Clear button**: empties `self.shapes`/selection, no confirmation.
- **Font scaling**: `_scale_ui_fonts` (same method/scale factor,
  `UI_FONT_SCALE=1.3`, as `inflate_polyhedron_app`) scales every named
  Tk/ttk font so the whole app's text grows together.
- Dark mode only (`sv_ttk.set_theme("dark")`, `ui_theme.PLOT_THEME`),
  like the other two apps.
- **File menu**: File → Load.../Save..., this app's only menu bar. See
  "Net JSON import/export" below.
- **Debug mode** ("d" key, same rationale as `Delete` — no text-entry
  widget to collide with): only changes whether `_redraw` draws a hover
  label on the nearest shape VERTEX (not an edge handle), reading
  `"vSHAPE.CORNER"` from that corner's OWN `(shape_id, corner)` — always
  its own address, never a shared-vertex union-find root (see
  `reference/design-history.md` for why, and what's lost by not showing
  shared roots).

### Net JSON import/export (File > Load/Save)

File format is exactly `stretchy_mesh.py`'s `{"name", "faces"}` vertex-loop
spec, plus two extra top-level keys only this app reads/writes:
`"net_layout"` (parallel to `"faces"`, each face's `{"cx","cy","rotation"}`)
and `"view"` (`{"scale": self.view_scale}`). Any other reader of the
format ignores unrecognized keys, so a saved file is a perfectly normal
net elsewhere too.

- **Save** (`on_save_clicked`): `_export_faces_and_layout` derives
  `"faces"` from `self.shapes`/`self.connections` via `_faces_from_shapes`,
  which unions `(shape_id, corner_index)` slots per connection —
  REVERSED (`a_edge` ↔ `b_edge+1`, `a_edge+1` ↔ `b_edge`), not
  straight-across, because a shared edge must run opposite directions in
  each face's loop (the winding convention `load_stretchy_mesh`
  enforces). `_vertex_roots` (no path compression) returns the raw
  `{slot: root}` mapping used directly by debug mode's own label (stable
  across unrelated edits); `_faces_from_shapes` layers a sequential-
  integer renumbering on top of it only for the exported JSON.
  `net_layout` is each shape's own `{"cx","cy","rotation"}`, same order
  as `self.shapes`. An unconnected edge just keeps its own unique id — an
  incomplete net saves fine as a legitimate open net.

  **`_validate_shapes_connections` runs in exactly ONE place: here, at
  Save — never live while a connection is being made.** (An earlier
  live full-merge-and-validate version was reverted after it rejected an
  entirely ordinary connection because of what some OTHER, unrelated
  connection's transitive merge implied about a shared vertex label — see
  `reference/design-history.md`.) It checks, on `self.shapes`/
  `self.connections` directly (before any export renumbering, so error
  messages use the same "vSHAPE.CORNER" identity debug mode shows): no
  shape's own edge may have its two corners' roots collapse together
  (self-loop), and no duplicate directed edge (mirrors
  `load_stretchy_mesh`). Every message names the specific chain of
  existing connections responsible, via `_connection_chain` (BFS over the
  same slot links `_vertex_roots` builds) — necessary because a conflict
  is never caused by one connection in isolation, only by a transitive
  chain of earlier ones. `NetValidationError` carries `self_loop_slots`
  so `on_save_clicked` can ring the offending corners
  (`SELF_LOOP_HIGHLIGHT_COLOR`, orange) on the canvas, persisting until
  the next actual edit.

  `_joined_points` (every already-connected `(shape_id, edge_index)`) is
  the one LIVE, permanent rule: an edge can only ever be joined once,
  independent of anything else — enforced by excluding a joined edge from
  handle hit-testing entirely.
- **Load** (`on_load_clicked`): requires `"faces"`; `_load_faces` fully
  replaces canvas state (never merges).
  - If `net_layout` is present and the same length as `faces`: use it
    directly, index-for-index — exact reproduction of a file this app
    saved.
  - Otherwise (any hand-authored net): `_layout_faces_with_gap(faces,
    root=0, gap=GAP)` — the same BFS-spanning-tree idea as
    `build_stretchy_net_layout`, reusing its `attach_polygon`/
    `regular_polygon_vertices` primitives directly, but with `GAP`
    (=`DEFAULT_SHAPE_EDGE_LENGTH`) of visible separation between faces
    since that function is untouchable and has no gap parameter.
  - `_infer_connections(faces)`: the opposite direction from Save's
    union-find — for every directed edge `(v,w)`, a reverse `(w,v)`
    elsewhere means a connection; no reverse partner means an open
    boundary edge. Self-loop edges (`v==w`, only from a pre-fix buggy
    save) are explicitly skipped, never inferred as connecting to
    themselves. `_self_loop_faces` runs first, purely diagnostically, so
    a malformed file still loads with a warning naming the bad edge.
  - A loaded file's vertex-id numbers are used ONLY transiently to infer
    connections — `_load_faces` immediately re-addresses every corner as
    fresh `(shape_id, edge_index)`, so a file's own labels never carry
    ongoing identity (by explicit design, to avoid treating incidental
    numbering as meaningful).
  - `_center_view_on_shapes` restores the saved `view.scale` (or 1.0 for
    a hand-authored file with no `"view"` section) and recenters on the
    loaded shapes' average center.

### Consumed by `inflate_polyhedron_app`'s "Net" panel

`on_select_net` there checks the loaded file for a `net_layout` section;
if present and the same length as `base_faces`,
`_layout_from_net_layout(faces, net_layout)` reproduces that EXACT saved
arrangement (each face's rigid transform, verified bit-for-bit equal to
this app's own math) instead of `build_stretchy_net_layout`'s fresh BFS
layout. Built at `stretchy_mesh.EDGE_LENGTH=1.0` and divided by
`DEFAULT_SHAPE_EDGE_LENGTH=70.0` to reproduce the same proportions at a
different scale. Also negates every point's final Y coordinate — a real
Tkinter-Y-down vs. matplotlib-Y-up convention mismatch, not a display
quirk (applied to the final assembled point, which equals reflecting the
whole rotated+translated result, so it's simpler than composing an
equivalent reflected rotation).

Important: this app never spatially snaps connected edges together (see
its own module docstring) — a reproduced `net_layout` can show two
connected faces with no line drawn between them (only the polygons
themselves are drawn) if the user left them apart on canvas. That's a
faithful reproduction, not what a physically unfolded net looks like.
`build_stretchy_net_layout`'s BFS fallback (any net with no `net_layout`)
is unaffected and always produces edge-to-edge faces.
