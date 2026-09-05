"""Shared fixture builders for tests/integration/.

An integration test exercises several utils sub-packages together (here:
geometry3d.hull_to_spec -> model.Polyhedron -> net_unfolder.NetUnfolder),
so its setup tends to be a multi-line construction rather than a single
call into one function. These small classes package that setup up so a
test itself reads as "build a polyhedron, unfold it, check a property"
instead of repeating the same coordinate/face-loop setup inline.
"""
import numpy as np

from utils.geometry3d.solid_coords import tetrahedron as _tetrahedron_coords
from utils.geometry3d.hull_to_spec import polyhedron_from_vertices
from utils.model.polyhedron import Polyhedron
from utils.net_unfolder import NetUnfolder


class TetraNetSpec:
    """A minimal 4-triangle tetrahedron, in both its normal closed form
    and an OPEN form with the 4th face omitted (an open triangular tray)
    -- see polyhedron_spec.py's module docstring for what an "open" net
    is under the vertices+faces format."""

    @staticmethod
    def _face_loops():
        vertices = _tetrahedron_coords()
        _, _, face_loops = polyhedron_from_vertices(vertices)
        return [np.array(v, dtype=float) for v in vertices], face_loops

    @staticmethod
    def build_open():
        """Drops the last face -- an open triangular tray, name 'Open Tetra'."""
        vertices, face_loops = TetraNetSpec._face_loops()
        return Polyhedron(vertices=vertices, faces=face_loops[:3], name="Open Tetra")

    @staticmethod
    def build_closed():
        vertices, face_loops = TetraNetSpec._face_loops()
        return Polyhedron(vertices=vertices, faces=face_loops, name="Closed Tetra")

    @staticmethod
    def unfold(polyhedron):
        return NetUnfolder.for_polyhedron(polyhedron)
