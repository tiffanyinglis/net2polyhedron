# Design history — interactive_builder_app

Rejected-approach narratives behind `SKILL.md`'s choices. Read only when
you need this reasoning.

## Palette icon preview

Ghost preview shows a solid selected-style fill. Two other looks were
tried and dropped: a dashed-outline-only preview (didn't read clearly as
"this is what you're about to place"), and before that a stippled fill
(Tk's stipple is a small fixed-pixel bitmap, tiled — read as
increasingly pixelated at placed-shape size, much bigger than a palette
icon).

## Color palette evolution

`POLYGON_COLORS` started as a single formula (even hue gradient, green →
blue → purple, flat lightness/saturation except a darker override for two
greens) rather than discrete swatches from `ui_theme.FACE_COLORS` (tried
first — the triangle alone went through navy, bright yellow, darkened
yellow, and a user-specified brown before being scrapped for the
gradient). The formula didn't survive later requests either: dropping the
first green and shifting the rest up, inserting a new hue between the
darker blue and purple, and independently adjusting two entries left the
hues unevenly spaced with several colors carrying their own overrides —
at that point an explicit per-entry table read more clearly than a
formula with a pile of exceptions. Current table is in `SKILL.md`.

## Edge connections: from two-click-per-shape to one-click-any-handle

Original design (`handle_points`, a set built only from the selected
shape's edges, the hovered shape's edges, and existing connection
endpoints) needed two clicks to start a connection: select the shape
first (to make its handles clickable via a since-removed
`_hit_test_edge_handle`, which only ever checked `self.selected_id`'s own
handles), then click a handle. Replaced at the user's explicit request
for one click straight onto any handle, selected or not — this is why
`_redraw` now considers every placed shape's every edge a candidate
handle regardless of selection.

Before that, a drag-out-a-line design (rather than click-click) was tried
first and replaced at the user's explicit request — see git history if
that version's reasoning is ever needed again.

## Hover hit-testing bug

Showing every free handle on every shape all the time was tried right
after the two-click design was dropped, and immediately read as clutter
with more than a couple of shapes — hence reveal-on-proximity
(`HANDLE_HIT_RADIUS`, deliberately the exact radius an actual click
needs, so a handle is never visible without being clickable).

A real bug the user reported: `_on_canvas_motion`'s hover check originally
used a plain point-in-polygon `_hit_test`, which lit up an entire shape as
a valid connection target the moment the cursor entered its body — even
nowhere near any handle — so a click that then missed every actual handle
would cancel with no connection despite the shape having looked ready a
moment earlier. Fixed by hit-testing PROXIMITY TO A HANDLE
(`_hit_test_any_edge_handle`) instead of the shape's body.

An earlier version of the "lit" highlight also lit the ENTIRE target
shape (mirroring a `lit_shape_ids` set checked against `shape["id"]`)
rather than just the one hovered edge — removed at the user's explicit
request, since it read as "this whole shape is selected" when only one
edge was about to connect.

## Live full-merge connection validation (reverted)

A second version of connection validation ran a full trial merge
(`_faces_from_shapes` on shapes+connections+the proposed one, checked
against a since-removed `_validate_faces`) before allowing ANY connection
to complete, reasoning that "an edge can only be joined once" alone wasn't
sufficient (two individually-free edges sharing a corner with connections
elsewhere could transitively collapse two different corners of some face
into one). That reasoning was correct but applying it LIVE was the wrong
call — reverted after a user hit it directly: two edges that looked like
an entirely ordinary connection were silently rejected because of what
some OTHER, already-existing connection elsewhere implied about a shared
vertex label. The actual lesson: during editing, every corner should be
treated as its own separate vertex regardless of what any other
connection's transitive merge currently implies — full merge-and-validate
is only meaningful once the whole net is being finalized, i.e. at Save.

An earlier Save-time validator (`_validate_faces`, still present as a
pure function, no longer called from Save) validated the ALREADY-exported
`faces` list, so a failed Save reported numbers that only existed in the
about-to-be-written JSON — meaningless to a user looking at shapes and
corners on screen. A user asked for exactly the current
`vSHAPE.CORNER`-identity error phrasing after chasing "self-loop edge at
vertex 37" against a file whose numbering didn't match the screen.

Real case `_connection_chain` caught, on `hippo.json`: shape 42 (already
attached to shape 34 on 3 of 5 edges) and shape 19 (also attached to shape
34) each had one matching free edge left; connecting shape 42 edge 3 to
shape 19 edge 4 looked reasonable but was off by one — the traced chain
went straight through the shared shape-34 attachment and showed shape
42's OWN edge 2 becoming a self-loop; edge 2 (not edge 3) turned out to be
the actual match, confirmed by trying it.

## Debug-mode vertex label: two reworks, both from real reports against `hippo.json`

Originally showed the EXPORTED sequential integer
(`_faces_from_shapes(...)[shape_index][corner]`) — reported as a bug:
`vertex_ids[root] = len(vertex_ids)` assigns ids in iteration order, so
one new, entirely unrelated connection elsewhere shifts every id assigned
after it, making an untouched corner's label change for no visible
reason. Fixed by extracting `_vertex_roots` (raw union-find, no
numbering) and showing the ROOT SLOT — stable across unrelated edits,
but a root can belong to a DIFFERENT, genuinely-connected shape than the
one hovered. On a big, densely-connected net (`hippo.json`, 42 shapes,
102 connections) most hovers then showed a foreign-looking label —
confusing on sight even though individually correct. The user asked for
every corner to always show its OWN polygon's number instead — the
current, final behavior.

What's lost: hovering two corners that already share an id no longer
shows matching text (previously useful for telling apart, e.g. for two
shapes already sharing one edge per `two_pentagons_and_a_square.json`'s
3-edge-shared example, which pairing of their remaining edges continues
the traversal). `_connection_chain` (see above) was added specifically to
cover that need a different way — spelling out the actual chain by name
rather than requiring a user to notice two hover labels match.

The label itself is white text on a 50%-alpha black box (a plain colored
canvas-text label was reported unreadable against some shape colors
underneath), sized to the label's own measured text extent.

## Rotation was originally `+=` then briefly `-=`, back to `+=`

Panning adds the drag's screen delta to the view offset directly
(dragging the background moves the view WITH the cursor). A `-=` version
(moving the view opposite the drag, like pulling the canvas out from
under a fixed viewport) was tried per an earlier request and then
explicitly reverted.

## Misc removed UI

A "Shapes" heading label above the palette (with its own hand-scaled
bold font tuple) was removed at the user's request; nothing in the left
panel needs a per-widget font override any more. A former
`_drop_shape` used to leave the newly-dropped shape selected — removed at
the user's request.
