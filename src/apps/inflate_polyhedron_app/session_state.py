"""Pydantic models for inflate_polyhedron_app's File > Save/Load: a full
on-screen session -- the chosen net, every parameter spinner, the
Convergence History table, the mesh (faces/positions/face_of_fine) at
every subdivision level reached so far, and each panel's own camera view
(zoom/pan/rotation) -- serialized to/from one JSON file, enough to reopen
a simulation exactly as left without re-running anything.

Pure data models with no Tkinter/app-object dependency -- app.py's
on_save_clicked/on_load_clicked build/apply a SessionStateModel using
their own already-imported state (FACE_COLORS, build_stretchy_net_layout,
etc.) directly, rather than this module reaching back into the app.
"""
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from pydantic import BaseModel


def edge_length_to_json(edge_length):
    """stretchy_mesh/mesh_levels' own edge_length: a uniform float (rare,
    pre-triangulation) or a {(a, b): length} dict (the normal, in-app
    form -- see mesh_levels.subdivide_once's own docstring). Returns a
    JSON-safe value: the float as-is, or the dict flattened to
    [[a, b, length], ...] (a JSON object can't be keyed by a tuple)."""
    if isinstance(edge_length, dict):
        return [[int(a), int(b), float(length)] for (a, b), length in edge_length.items()]
    return float(edge_length)


def edge_length_from_json(value):
    """Inverse of edge_length_to_json."""
    if isinstance(value, list):
        return {(a, b): length for a, b, length in value}
    return value


class LevelStateModel(BaseModel):
    """One subdivision level's own mesh: faces/positions/face_of_fine --
    exactly what draw()/_draw_level_panel need to redisplay it -- plus
    edge_length, only meaningful for the CURRENT frontier level (where
    relax_once/subdivide_once need it to continue; an already-left,
    frozen level has no use for it, matching self.level_snapshots' own
    faces/positions/face_of_fine-only shape)."""
    faces: List[List[int]]
    positions: Dict[int, Tuple[float, float, float]]
    face_of_fine: List[int]
    edge_length: Optional[Union[float, List[Tuple[int, int, float]]]] = None

    @classmethod
    def from_mesh(cls, faces, positions, face_of_fine, edge_length=None):
        return cls(
            faces=[list(face) for face in faces],
            positions={int(v): (float(p[0]), float(p[1]), float(p[2]))
                       for v, p in positions.items()},
            face_of_fine=list(face_of_fine),
            edge_length=edge_length_to_json(edge_length) if edge_length is not None else None,
        )

    def to_mesh(self):
        """Returns (faces, positions, face_of_fine, edge_length), the
        inverse of from_mesh -- positions as {vertex_id: np.ndarray(3,)},
        matching stretchy_mesh's own representation."""
        positions = {v: np.array(p, dtype=float) for v, p in self.positions.items()}
        edge_length = (edge_length_from_json(self.edge_length)
                        if self.edge_length is not None else None)
        return [list(face) for face in self.faces], positions, list(self.face_of_fine), edge_length


class LevelHistoryRecordModel(BaseModel):
    """Mirrors one row of InflatePolyhedronApp.level_history exactly (see
    its own _record_level_history docstring). precomp_time_s/sim_time_s
    (2026-09-16, explicit user request -- a loaded session's own
    Convergence History showed no Simulation Time at all, since these two
    used to be dropped as "extra" fields pydantic silently ignores,
    per an earlier "timing is a live-session diagnostic, not persistent
    state" decision) ARE saved now too -- "Simulation Time" (renamed from
    "Elapsed Time" 2026-09-17)/"Cumulative Time" being release-mode-
    visible columns, not debug-only, is what actually changed since that
    original call. Field names themselves are unchanged by that rename --
    only the UI-facing column id/label ("simulation_time"/"Simulation
    Time" in app.py) moved, so an older saved session still loads here
    with no migration needed."""
    pressure: Optional[float] = None
    steps: int = 0
    max_stretch_pct: float = 0.0
    # Optional now (2026-09-17, explicit user request -- "RMS stretch %"
    # shows "--" for the whole Computing phase, backed by a genuine
    # `None` in app.py's own self.level_history, not a 0.0 placeholder --
    # see _record_level_history's own comment) -- a Save while a run is
    # actively computing (the File menu isn't disabled during a run, see
    # _set_controls_enabled's own widget list) would otherwise fail
    # Pydantic validation entirely, right when Save is invoked.
    rms_stretch_pct: Optional[float] = None
    optimality: Optional[float] = None
    converged: Optional[bool] = None
    gtol: float
    target_rms_pct: Optional[float] = None
    precomp_time_s: Optional[float] = None
    sim_time_s: Optional[float] = None


class LastStatsModel(BaseModel):
    """Mirrors InflatePolyhedronApp.last_stats -- the current frontier
    level's own live stats (see _compute_stretch_stats/relax_once).
    rms_stretch_pct is Optional -- same "--"-while-computing sentinel as
    LevelHistoryRecordModel's own field, see its comment."""
    max_stretch_pct: float = 0.0
    rms_stretch_pct: Optional[float] = None
    optimality: Optional[float] = None
    converged: Optional[bool] = None
    gtol: Optional[float] = None
    target_rms_pct: Optional[float] = None


class SessionStateModel(BaseModel):
    """One full on-screen simulation session for inflate_polyhedron_app
    -- everything File > Save writes and File > Load restores: the net
    (base_faces/net_name/net_file), every parameter spinner
    (target_rms_pct per level, tolerance), the Convergence History table
    (level_history), and each subdivision level reached so far's own mesh
    (levels)."""
    net_name: str
    base_faces: List[List[int]]
    # The ORIGINAL net .json file's own parsed content (whatever
    # on_select_net read from data/input/stretchy_nets/*.json, or a
    # previously-loaded session's own copy of it) -- carries extras
    # base_faces alone doesn't, e.g. a "net_layout" section written by
    # interactive_builder_app, which is what the "Net" panel next to
    # Level 0 actually needs to reproduce a hand-arranged net's exact
    # on-screen layout rather than falling back to a fresh BFS one (see
    # on_select_net's own comment). None only if a session was somehow
    # saved with no net file behind it at all.
    net_file: Optional[Dict[str, Any]] = None
    subdivision_level: int
    # Optional now (2026-09-17, explicit user request -- "the pressure
    # should also be -- until things converge"): app.py's own
    # self.pressure_value is a genuine `None` for the whole Computing
    # phase (see on_inflate_clicked's own comment), and the File menu
    # isn't disabled during a run (_set_controls_enabled's own widget
    # list), so a Save mid-run needs this to validate too. on_load_
    # session_clicked falls back to DEFAULT_PRESSURE when None, same as
    # __init__'s own starting value.
    pressure_value: Optional[float] = None
    iteration_count: int
    debug_mode: bool
    tolerance: str
    target_rms_pct: Dict[int, float]
    last_stats: LastStatsModel
    level_history: Dict[int, LevelHistoryRecordModel]
    levels: Dict[int, LevelStateModel]
    # Levels 1-3's own SHARED camera state (self._level13_camera in
    # app.py -- see _render_level_pv) and the Net panel's own separate
    # self.net_zoom/_pan (_draw_target_faces) -- added once these became
    # persistent-feeling, explicitly-adjusted view settings (pan/zoom/
    # rotation resets, wider zoom range, etc.) rather than incidental
    # defaults. Field names kept as the ORIGINAL "level_*" (not renamed
    # to "level13_*") even though Level 0 split off into its own
    # independent camera (self._level0_camera, level0_zoom/_pan/_rotation
    # below, 2026-09-17 explicit user request -- "separate the zoom/
    # rotation/translation of level 0 from level 1-3 since they look so
    # different") -- an OLDER session file's own single camera (from
    # before that split, when every level including 0 shared it) maps
    # naturally onto "the Levels 1-3 group" this way, with no migration
    # needed; only level0_zoom/_pan/_rotation being absent (None) makes
    # Level 0 fall back to a FRESH default rather than inheriting
    # whatever that old file's one shared camera happened to be.
    # All optional with a default that reproduces the ORIGINAL always-
    # reset-to-default behavior, so a session file saved before ANY of
    # this existed still loads exactly as it used to -- app.py falls back
    # to _initial_level_rotation() (not a baked-in quaternion here) when
    # a rotation field is None, since that method is the one place that
    # non-axis-aligned starting view is actually defined.
    level_zoom: float = 1.0
    level_pan: Tuple[float, float] = (0.0, 0.0)
    level_rotation: Optional[Tuple[float, float, float, float]] = None  # scipy Rotation (x, y, z, w)
    level0_zoom: float = 1.0
    level0_pan: Tuple[float, float] = (0.0, 0.0)
    level0_rotation: Optional[Tuple[float, float, float, float]] = None  # scipy Rotation (x, y, z, w)
    net_zoom: float = 1.0
    net_pan: Tuple[float, float] = (0.0, 0.0)
