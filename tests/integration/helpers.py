"""Shared fixture builders for tests/integration/.

An integration test exercises several utils sub-packages together (here:
persistence.polyhedron_spec -> geometry3d.Polyhedron -> polyhedron_unfolder.NetUnfolder),
so its setup tends to be a multi-line construction rather than a single
call into one function. These small classes package that setup up so a
test itself reads as "build a polyhedron, unfold it, check a property"
instead of repeating the same load/face-slice setup inline.
"""
from common.paths import NETS_DIR
from utils.persistence.polyhedron_spec import load_polyhedron_spec
from utils.geometry3d.polyhedron import Polyhedron
from utils.polyhedron_unfolder import NetUnfolder


class TetraNetSpec:
    """A minimal 4-triangle tetrahedron, in both its normal closed form
    and an OPEN form with the 4th face omitted (an open triangular tray)
    -- see polyhedron_spec.py's module docstring for what an "open" net
    is under the vertices+faces format. Loaded straight from
    data/input/nets/tetrahedron.json (the settled, canonical tetrahedron)
    rather than re-derived from raw coordinates."""

    @staticmethod
    def _vertices_and_faces():
        vertices, faces, _ = load_polyhedron_spec(NETS_DIR / "tetrahedron.json")
        return vertices, faces

    @staticmethod
    def build_open():
        """Drops the last face -- an open triangular tray, name 'Open Tetra'."""
        vertices, faces = TetraNetSpec._vertices_and_faces()
        return Polyhedron(vertices=vertices, faces=faces[:3], name="Open Tetra")

    @staticmethod
    def build_closed():
        vertices, faces = TetraNetSpec._vertices_and_faces()
        return Polyhedron(vertices=vertices, faces=faces, name="Closed Tetra")

    @staticmethod
    def unfold(polyhedron):
        return NetUnfolder.for_polyhedron(polyhedron)
