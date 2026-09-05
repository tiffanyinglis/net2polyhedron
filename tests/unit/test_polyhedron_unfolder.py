import numpy as np

from utils.polyhedron_unfolder import Hinge, face_normal, fold_transforms, hinge_transform
from utils.polyhedron import Polyhedron


def test_hinge_stores_its_fields_verbatim():
    hinge = Hinge(parent_id=0, child_id=1, parent_edge_idx=2, child_edge_idx=0, angle=1.23)
    assert hinge.parent_id == 0
    assert hinge.child_id == 1
    assert hinge.parent_edge_idx == 2
    assert hinge.child_edge_idx == 0
    assert hinge.angle == 1.23


def test_hinge_transform_is_a_pure_rotation_about_an_offset_axis():
    # Rotate 90 degrees about the vertical line through (1, 0, 0) --
    # (1, 0, 5) sits ON that axis so it must map to itself; (2, 0, 0), one
    # unit off-axis along +x, must swing to +y around it.
    M = hinge_transform(axis_point=np.array([1.0, 0.0, 0.0]),
                         axis_dir=np.array([0.0, 0.0, 1.0]),
                         angle=np.pi / 2)
    on_axis = M @ np.array([1.0, 0.0, 5.0, 1.0])
    assert np.allclose(on_axis[:3], [1.0, 0.0, 5.0])
    off_axis = M @ np.array([2.0, 0.0, 0.0, 1.0])
    assert np.allclose(off_axis[:3], [1.0, 1.0, 0.0], atol=1e-10)


def test_face_normal_points_outward_for_a_simple_ccw_square():
    # A unit square in the z=0 plane, CCW as seen from +z -- given this
    # winding, "outward" must be exactly +z.
    pts = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]])
    normal = face_normal(pts)
    assert np.allclose(normal, [0.0, 0.0, 1.0])


def test_fold_transforms_root_is_always_identity():
    """A single-face, hingeless flat net is enough to isolate this
    invariant -- the deeper "does a real hinge tree actually fold into a
    real solid" property is already covered at the UnfoldablePolyhedron
    level (test_unfoldable_polyhedron.py), which calls fold_transforms
    via a real spanning tree over a real Polyhedron."""
    flat = Polyhedron(vertices=[np.array(v) for v in [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]],
                       faces=[(0, 1, 2, 3)])
    for t in (0.0, 0.5, 1.0):
        transforms = fold_transforms(flat, root=0, hinges=[], t=t)
        assert np.allclose(transforms[0], np.eye(4))
