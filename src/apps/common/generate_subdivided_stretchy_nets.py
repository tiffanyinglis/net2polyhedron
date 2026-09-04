"""Generator: writes data/input/stretchy_nets/<name>_res<resolution>.json --
a fine triangulated "fabric" version of an existing coarse stretchy net
(data/input/stretchy_nets/<name>.json), via
utils.subdivisions.mesh_subdivide.subdivide_mesh (see that module's
docstring for how the subdivision is built and merged across shared
coarse edges into one connected mesh).

    python src/apps/common/generate_subdivided_stretchy_nets.py

Written as an EXTENDED vertex-loop mesh: the ordinary "faces" (the fine
triangulation, for combinatorics/solving) plus "coarse_faces" (the
original, un-subdivided polygon loops), "resolution", and "face_of_fine"
(fine_faces[i] belongs to coarse_faces[face_of_fine[i]]). A plain
stretchy-net reader that only looks at "faces" still works unmodified
(extra keys are just ignored) -- but
utils.subdivisions.mesh_subdivide.load_fabric_spec picks up the extra
fields so utils.persistence.stretchy_cache can solve this via
solve_fabric_mesh (draping the fine mesh over the COARSE net's own
correctly-shaped, correctly-rounded solve) instead of plain
solve_wireframe(faces) at a uniform edge_length=1.0. That distinction
matters a lot here: tried first, plain solve_wireframe on a subdivided
cube took ~13 minutes and settled into a generic rounded blob, not a
recognizable cube -- forcing every fine edge (rim, or a diagonal-split
segment ~sqrt(2) times longer) to the same rest length erases exactly the
shape information that makes it look like a cube. See mesh_subdivide.py's
and stretchy_cache.py's docstrings for the full story.

inflate_polyhedron_app also reads "coarse_faces"/"face_of_fine" at
render time, so a fabric net's left panel shows the coarse polygons
(with a faint subdivision overlay) instead of hundreds of individual
fine triangles, and its right panel colors every fine triangle by its
original coarse face.
"""
import json
import os

from paths import STRETCHY_NETS_DIR
from utils.geometry3d.stretchy_mesh import load_stretchy_mesh
from utils.subdivisions.mesh_subdivide import subdivide_mesh

# (source net basename, resolution) pairs to generate -- add more here to
# try other nets/resolutions; subdivide_mesh does the actual work for
# whatever's listed. Kept as an editable list (like
# generate_stretchy_platonic_nets.py's PLATONIC_SOLIDS) rather than CLI
# args, since this is meant to be tweaked and rerun during exploration.
#
# "cube" at resolution 3 (not 4): SUBDIVISIONS[4] switched from a
# 2-triangle diagonal split to a 4-triangle centroid fan (see
# utils/subdivisions/polygon_subdivisions.py's docstring -- the diagonal split
# gave two of the cube's 8 corners a lower mesh valence than the other
# six, an asymmetry invisible at modest pressure but visibly lopsided at
# high pressure). That doubles the coarse triangle count per face, so
# resolution 3 here (6 faces * 4 coarse * 3**2 = 216 fine triangles)
# lands close to what resolution 4 under the OLD 2-triangle split used
# to produce (192), rather than resolution 4 under the new split (384).
#
# The other Platonic solids are all single-n-gon nets (every face the
# same n), so subdivide_mesh's per-face resolution_for(n, 3) is applied
# uniformly across the whole net with no shared-edge resolution mismatch
# to worry about (see mesh_subdivide.subdivide_mesh's docstring -- that's
# only a concern for a MIXED-n net like two_pentagons_and_a_square,
# skipped here for that reason). "3" below is the shared nominal base
# resolution passed to resolution_for, not the literal per-face
# resolution -- e.g. resolution_for(3, 3) == 4, so tetrahedron/octahedron/
# icosahedron's triangular faces are actually subdivided at resolution 4
# each, and dodecahedron's pentagons at resolution_for(5, 3) == 4.
SUBDIVISIONS_TO_GENERATE = [
    ("cube", 3),
    ("tetrahedron", 3),
    ("octahedron", 3),
    ("icosahedron", 3),
    ("dodecahedron", 3),
]


def main():
    for name, resolution in SUBDIVISIONS_TO_GENERATE:
        src_path = os.path.join(STRETCHY_NETS_DIR, f"{name}.json")
        coarse_faces, coarse_name = load_stretchy_mesh(src_path)
        fine_faces, face_of_fine, _, _ = subdivide_mesh(coarse_faces, resolution)
        faces = [list(f) for f in fine_faces]
        n_verts = len({v for f in faces for v in f})
        spec = {
            "name": f"{coarse_name} (res{resolution})",
            "coarse_faces": [list(f) for f in coarse_faces],
            "resolution": resolution,
            "faces": faces,
            "face_of_fine": list(face_of_fine),
        }
        out_path = os.path.join(STRETCHY_NETS_DIR, f"{name}_res{resolution}.json")
        with open(out_path, "w") as f:
            json.dump(spec, f, indent=2)
            f.write("\n")
        print(f"wrote {out_path}  ({len(faces)} faces, {n_verts} vertices)")


if __name__ == "__main__":
    main()
