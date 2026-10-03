import { type Vec3, add, cross, dot, mean, norm, safeUnit, scale, sub, zero } from "./vec3";
import { edgeKey } from "./mesh";

export const REPULSION_STRENGTH = 0.015;
export const MIN_REPULSION_DISTANCE = 0.05;

/** Plain Hooke's-law linear spring force shared by Level 0's spring-only relax and Level 1+'s
 * full relax (mirrors stretchy_mesh._relax_force's spring term / pre_inflation_relaxer.
 * _spring_only_force -- both now the same law, see physics.md). */
export function springForce(
  pts: Vec3[],
  edgeA: number[],
  edgeB: number[],
  restLengths: number[],
): Vec3[] {
  const force = pts.map(zero);
  for (let i = 0; i < edgeA.length; i++) {
    const a = edgeA[i];
    const b = edgeB[i];
    const rest = restLengths[i];
    const diff = sub(pts[b], pts[a]);
    const dist = norm(diff);
    const dir = safeUnit(diff);
    const stretch = (dist - rest) / rest;
    const f = scale(dir, stretch);
    force[a] = add(force[a], f);
    force[b] = sub(force[b], f);
  }
  return force;
}

/** Each face's own area vector (Newell's method, `0.5 * sum cross(p_i, p_{i+1})`) -- magnitude is
 * area, direction is the outward normal implied by the face's own CCW winding. */
function faceAreaVector(facePts: Vec3[]): Vec3 {
  const n = facePts.length;
  let v = zero();
  for (let i = 0; i < n; i++) v = add(v, cross(facePts[i], facePts[(i + 1) % n]));
  return scale(v, 0.5);
}

/** `pressure * area * outward_normal`, split evenly across each face's own vertices (mirrors
 * stretchy_mesh._relax_force's pressure term / pre_inflation_relaxer._pressure_only_force).
 * `excludeFace`, if given, zeroes out a face entirely (an "open" wedge with no glued partner). */
export function pressureForce(
  pts: Vec3[],
  faces: number[][],
  pressure: number,
  excludeFace?: (faceIndex: number) => boolean,
): Vec3[] {
  const force = pts.map(zero);
  if (!pressure) return force;
  faces.forEach((face, i) => {
    if (excludeFace?.(i)) return;
    const n = face.length;
    const areaVec = faceAreaVector(face.map((v) => pts[v]));
    const perVertex = scale(areaVec, pressure / n);
    for (const v of face) force[v] = add(force[v], perVertex);
  });
  return force;
}

/** All-pairs inverse-square repulsion (mirrors stretchy_mesh.repulsion_force). `indices`, if
 * given, restricts both which vertices repel each other and which receive any force to that
 * subset -- everyone else gets zero here. `multipliers` scales each subset vertex's own
 * contribution (product of the two vertices' own multiplier, like a product of charges). */
export function repulsionForce(
  pts: Vec3[],
  strength = REPULSION_STRENGTH,
  indices?: number[],
  multipliers?: number[],
): Vec3[] {
  const force = pts.map(zero);
  const subset = indices ?? pts.map((_, i) => i);
  const mult = multipliers ?? subset.map(() => 1);
  for (let i = 0; i < subset.length; i++) {
    for (let j = i + 1; j < subset.length; j++) {
      const vi = subset[i];
      const vj = subset[j];
      const diff = sub(pts[vi], pts[vj]);
      const dist = Math.max(norm(diff), MIN_REPULSION_DISTANCE);
      const magnitude = (strength * mult[i] * mult[j]) / (dist * dist);
      const f = scale(diff, magnitude / dist);
      force[vi] = add(force[vi], f);
      force[vj] = sub(force[vj], f);
    }
  }
  return force;
}

/** Each vertex's own outward direction as the normalized sum of its incident faces' unit normals
 * (mirrors stretchy_mesh._vertex_outward_normals). A vertex with no well-defined direction (faces
 * cancel, or touches only excluded faces) gets the genuine zero vector, not a fallback axis. */
export function vertexOutwardNormals(
  pts: Vec3[],
  faces: number[][],
  excludeFace?: (faceIndex: number) => boolean,
): Vec3[] {
  const sums = pts.map(zero);
  faces.forEach((face, i) => {
    if (excludeFace?.(i)) return;
    const areaVec = faceAreaVector(face.map((v) => pts[v]));
    const len = norm(areaVec);
    if (len < 1e-12) return;
    const unit = scale(areaVec, 1 / len);
    for (const v of face) sums[v] = add(sums[v], unit);
  });
  return sums.map((s) => {
    const len = norm(s);
    return len > 1e-12 ? scale(s, 1 / len) : zero();
  });
}

/** Each face's normal sign (+1/-1, 0 if degenerate) relative to "pointing outward from the
 * mesh's overall centroid" (mirrors stretchy_mesh._orientation_signs). */
export function orientationSigns(pts: Vec3[], faces: number[][]): number[] {
  const centroid = mean(pts);
  return faces.map((face) => {
    const facePts = face.map((v) => pts[v]);
    const normal = cross(sub(facePts[1], facePts[0]), sub(facePts[2], facePts[0]));
    const normalLen = norm(normal);
    const outward = sub(mean(facePts), centroid);
    const outwardLen = norm(outward);
    if (normalLen < 1e-9 || outwardLen < 1e-9) return 0;
    return Math.sign(dot(scale(normal, 1 / normalLen), scale(outward, 1 / outwardLen)));
  });
}

/** Mesh's current total signed enclosed volume, via the divergence theorem over a centroid-free
 * fan triangulation of every face from its own first vertex (mirrors stretchy_mesh._mesh_volume /
 * mesh_volume). Meaningful only for a closed mesh -- an open net's own "volume" has no fixed
 * sign to speak of, used here only for the inside-out check, which already guards for that. */
export function meshVolume(pts: Vec3[], faces: number[][]): number {
  let total = 0;
  for (const face of faces) {
    const v0 = pts[face[0]];
    for (let i = 1; i < face.length - 1; i++) {
      total += dot(v0, cross(pts[face[i]], pts[face[i + 1]])) / 6;
    }
  }
  return total;
}

/** Exact total rest surface area: closed-form regular-polygon area per face for a uniform scalar
 * edge length, else Heron's formula per triangle for a per-edge rest-length map -- correct even
 * with mixed rest lengths (a fan-triangulated mesh's wedge triangles have a short spoke and a
 * long rim edge, not a uniform side length) unlike assuming every face is regular (mirrors
 * stretchy_mesh._total_rest_area, including its own "every dict-keyed mesh here is all-triangle"
 * assumption). */
export function totalRestArea(faces: number[][], edgeLength: number | Map<string, number>): number {
  if (typeof edgeLength === "number") {
    let total = 0;
    for (const face of faces) {
      const n = face.length;
      total += (n / 4 / Math.tan(Math.PI / n)) * edgeLength * edgeLength;
    }
    return total;
  }
  let total = 0;
  for (const [a, b, c] of faces) {
    const la = edgeLength.get(edgeKey(b, c))!;
    const lb = edgeLength.get(edgeKey(a, c))!;
    const lc = edgeLength.get(edgeKey(a, b))!;
    const s = (la + lb + lc) / 2;
    total += Math.sqrt(Math.max(0, s * (s - la) * (s - lb) * (s - lc)));
  }
  return total;
}
