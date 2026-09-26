"""Pydantic model for interactive_inflater_app's File > Save Session/Load Session: a full
on-screen session as a ".hippie" file -- the whole live net (EVERY placed shape/connection, not
just the central object), the anchor, the central object's own current mesh at whatever
subdivision level it last reached, every parameter spinner, and the pressure/level-history state
needed to seed a later Diff Inflate.

A .hippie deliberately mirrors inflate_polyhedron_app's own .hippo (SessionStateModel, imported
from inflate_polyhedron_app.session_state and reused here for the single current-level mesh --
LevelStateModel is a plain, app-agnostic schema, see its own docstring) rather than replacing it:
this app only ever tracks ONE flat mesh (the central object's) at a time, not one per
subdivision level reached, so there is no `levels: Dict[int, LevelStateModel]` here the way
.hippo has -- just one `mesh: LevelStateModel` field.

The one thing a .hippo file structurally cannot represent at all is what makes a .hippie
different: `net_file` here may describe MORE THAN ONE connected piece (every OTHER net-writing
path in this project -- interactive_builder_app's own Save -- explicitly forbids that, see the
net-fold-project skill's untouchable.md). `anchor_shape_id` records which placed shape (by its
own saved `net_layout` "shape_id", NOT necessarily the live id it gets reassigned on the next
Load -- see interactive_inflater_app.app's own Load Session docstring for the index-based remap
this requires) was the central-object anchor at save time.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from inflate_polyhedron_app.session_state import LevelStateModel


class InflaterSessionStateModel(BaseModel):
    """One full interactive_inflater_app session. `net_file` is the FULL net (every shape/
    connection currently placed, central or not) exactly as BuilderPane.export_full_net_dict()
    builds it -- a plain vertex-loop mesh dict plus this project's own net_layout/
    builder_connections/source_polygon_id extension fields, the same shape interactive_builder_app
    itself saves, just not restricted to one connected piece. `base_faces`/`mesh`/
    `subdivision_level` describe ONLY the CENTRAL object (the piece containing `anchor_shape_id`)
    -- the only piece ever actually inflated, matching what InflaterPane.base_faces/faces/
    positions/face_of_fine/subdivision_level hold live."""
    net_name: str
    net_file: Dict[str, Any]
    anchor_shape_id: int
    base_faces: List[List[int]]
    subdivision_level: int
    mesh: LevelStateModel
    tolerance: str
    target_rms_pct: Dict[int, float]
    last_pressure: Optional[float] = None
    # {level: {"pressure", "rms_stretch_pct", "pressure_found"}} -- InflaterPane's own live
    # in-memory shape (see its own self.level_history docstring), stored as plain dicts rather
    # than a dedicated model since it's never anything but this one app's own internal cache, fed
    # straight back into self.level_history on load with no translation needed either way.
    level_history: Dict[int, Dict[str, Any]] = {}
