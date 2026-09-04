"""Shared fixture builders for tests/integration/.

An integration test exercises several utils sub-packages together (here:
persistence.polyhedron_spec -> model.PolyhedralNet -> geometry3d.net_fold_core),
so its setup tends to be a multi-line net spec rather than a single call
into one function. These small classes package that setup up so a test
itself reads as "build a net, load it, check a property" instead of
repeating write_polyhedron_spec's full argument list inline.
"""
from utils.persistence.polyhedron_spec import write_polyhedron_spec
from utils.model import PolyhedralNet


class TetraNetSpec:
    """A minimal 4-triangle tetrahedron net, in both its normal closed form
    and an OPEN form with the 4th face omitted (an open triangular tray) --
    see polyhedron_spec.py's module docstring for what "omit"/"hidden" mean.
    """
    DEGREES = [3, 3, 3, 3]

    @staticmethod
    def write_open(path):
        # Face 3 omitted: net/extra span only faces 0-2 (a spanning tree of
        # 2 edges over 3 kept faces), hidden carries every edge touching the
        # omitted face -- same shape of spec tools/generate_open_dodecahedron_nets.py
        # produces for half_dodecahedron.json / dodecahedron_minus_one.json.
        write_polyhedron_spec(str(path), TetraNetSpec.DEGREES, [(0, 1), (0, 2)], [(1, 2)],
                               name="Open Tetra", omitted={3},
                               hidden_edges=[(0, 3), (1, 3), (2, 3)])

    @staticmethod
    def write_closed(path):
        write_polyhedron_spec(str(path), TetraNetSpec.DEGREES,
                               [(0, 1), (0, 2), (0, 3)], [(1, 2), (1, 3), (2, 3)],
                               name="Closed Tetra")

    @staticmethod
    def load(path):
        # The no-cache slow path (spec parse -> EdgeMap -> layout -> solve),
        # not PolyhedralNet.load()'s .fold-cache-dispatching entry point --
        # these tests don't want a cache directory created as a side effect.
        return PolyhedralNet._load_json_uncached(str(path))
