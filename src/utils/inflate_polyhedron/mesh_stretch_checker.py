"""Turns a solved mesh's flat (N,3) positions into a {vertex_id: pos}
dict plus its own max/RMS edge-stretch percentages -- shared by
relax_once, relax_initial_configuration, and multi_trial_inflater's own
per-trial stretch reading. RMS is what pressure calibration/convergence
target reads against (an irregular/subdivided mesh stretches unevenly);
max is a debug-only display stat elsewhere (inflate_polyhedron_app's
Convergence History table) -- this module always computes both, callers
pick which one they need."""
import numpy as np


def positions_and_stretch(pts, vertex_ids, edges, length_arr, rms_exclude_edges=None):
    """pts: (N,3) flat solved positions; vertex_ids: the ids `pts`' own
    rows correspond to, in order; edges: (a, b) vertex-id pairs; length_arr:
    each edge's own rest length (a scalar-broadcastable array, or a dict-
    derived array already in `edges`' own order -- see
    stretchy_mesh._edge_setup). Returns (positions dict, max_stretch_pct,
    rms_stretch_pct).

    `rms_exclude_edges`, if given, is a set of (a, b) SORTED vertex-id-pair
    tuples to omit from the RMS stat -- `max_stretch_pct` always still
    uses every edge (e.g. an OPEN polygon's own edges shouldn't drive the
    reported/target RMS). Membership is checked per edge rather than
    requiring a mask the same length/order as `edges`. Falls back to
    including every edge if the exclusion would otherwise leave nothing
    to average, rather than producing a NaN."""
    positions = {v: pts[i] for i, v in enumerate(vertex_ids)}
    lengths = np.array([np.linalg.norm(positions[a] - positions[b]) for a, b in edges])
    stretch_pct = 100 * (lengths - length_arr) / length_arr
    max_stretch_pct = float(np.max(np.abs(stretch_pct)))
    rms_stretch_pct = float(np.sqrt(np.mean(stretch_pct ** 2)))
    if rms_exclude_edges:
        rms_mask = np.array([tuple(sorted(e)) not in rms_exclude_edges for e in edges])
        if rms_mask.any() and not rms_mask.all():
            rms_stretch_pct = float(np.sqrt(np.mean(stretch_pct[rms_mask] ** 2)))
    return positions, max_stretch_pct, rms_stretch_pct
