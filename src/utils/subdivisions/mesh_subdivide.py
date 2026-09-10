"""Reads the "coarse_faces"/"resolution"/"face_of_fine" fields a legacy
fabric-subdivided stretchy net .json (see inflate_polyhedron_app's module
docstring) may carry alongside its ordinary "faces" -- the actual fine-mesh
generation and solving this format used to need (subdivide_mesh,
solve_fabric_mesh) is gone now that inflate_polyhedron_app builds its own
starting configuration for every net, coarse or fabric, via
stretchy_mesh.relax_initial_configuration; a fabric file's baked-in fine
mesh is no longer read at all, only its "coarse_faces".
"""
import json


def load_fabric_spec(path):
    """path: a stretchy net .json. If it's fabric-subdivided (carrying
    "coarse_faces"/"resolution"/"face_of_fine" alongside "faces"), returns
    (coarse_faces, resolution, face_of_fine); otherwise returns (None,
    None, None)."""
    with open(path) as f:
        spec = json.load(f)
    coarse_faces = spec.get("coarse_faces")
    if not coarse_faces:
        return None, None, None
    return coarse_faces, spec["resolution"], spec["face_of_fine"]
