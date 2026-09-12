"""Pydantic models for inflate_polyhedron_app's File > Save/Load: a full
on-screen session -- the chosen net, every parameter spinner, the
Convergence History table, and the mesh (faces/positions/face_of_fine) at
every subdivision level reached so far -- serialized to/from one JSON
file, enough to reopen a simulation exactly as left without re-running
anything.

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
    its own _record_level_history docstring)."""
    pressure: Optional[float] = None
    steps: int = 0
    max_stretch_pct: float = 0.0
    rms_stretch_pct: float = 0.0
    optimality: Optional[float] = None
    converged: Optional[bool] = None
    gtol: float
    target_rms_pct: Optional[float] = None


class LastStatsModel(BaseModel):
    """Mirrors InflatePolyhedronApp.last_stats -- the current frontier
    level's own live stats (see _compute_stretch_stats/relax_once)."""
    max_stretch_pct: float = 0.0
    rms_stretch_pct: float = 0.0
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
    pressure_value: float
    iteration_count: int
    debug_mode: bool
    tolerance: str
    target_rms_pct: Dict[int, float]
    last_stats: LastStatsModel
    level_history: Dict[int, LevelHistoryRecordModel]
    levels: Dict[int, LevelStateModel]
