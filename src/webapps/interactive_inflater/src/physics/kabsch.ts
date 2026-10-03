import { type Vec3, add, mean, sub } from "./vec3";

type Mat3 = [[number, number, number], [number, number, number], [number, number, number]];

function zeros3(): Mat3 {
  return [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
}

function transpose3(m: Mat3): Mat3 {
  const r = zeros3();
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) r[i][j] = m[j][i];
  return r;
}

function multiply3(a: Mat3, b: Mat3): Mat3 {
  const r = zeros3();
  for (let i = 0; i < 3; i++)
    for (let j = 0; j < 3; j++)
      for (let k = 0; k < 3; k++) r[i][j] += a[i][k] * b[k][j];
  return r;
}

function mulVec3(m: Mat3, v: Vec3): Vec3 {
  return [
    m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
    m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
    m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
  ];
}

function det3(m: Mat3): number {
  return (
    m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) -
    m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) +
    m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
  );
}

/** Cyclic Jacobi eigenvalue algorithm for a symmetric 3x3 matrix -- a fixed sweep count is
 * plenty for a 3x3 case. Returns eigenvalues and eigenvectors as columns of a rotation matrix. */
function jacobiEigenSymmetric3(input: Mat3): { values: [number, number, number]; vectors: Mat3 } {
  const a: Mat3 = [[...input[0]], [...input[1]], [...input[2]]] as Mat3;
  let v: Mat3 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  const pairs: [number, number][] = [[0, 1], [0, 2], [1, 2]];
  for (let sweep = 0; sweep < 30; sweep++) {
    let offDiag = 0;
    for (const [p, q] of pairs) offDiag += a[p][q] * a[p][q];
    if (offDiag < 1e-28) break;
    for (const [p, q] of pairs) {
      if (Math.abs(a[p][q]) < 1e-15) continue;
      const theta = (a[q][q] - a[p][p]) / (2 * a[p][q]);
      const t = Math.sign(theta || 1) / (Math.abs(theta) + Math.sqrt(theta * theta + 1));
      const c = 1 / Math.sqrt(t * t + 1);
      const s = t * c;
      const app = a[p][p];
      const aqq = a[q][q];
      const apq = a[p][q];
      a[p][p] = c * c * app - 2 * s * c * apq + s * s * aqq;
      a[q][q] = s * s * app + 2 * s * c * apq + c * c * aqq;
      a[p][q] = 0;
      a[q][p] = 0;
      for (let i = 0; i < 3; i++) {
        if (i !== p && i !== q) {
          const aip = a[i][p];
          const aiq = a[i][q];
          a[i][p] = c * aip - s * aiq;
          a[p][i] = a[i][p];
          a[i][q] = s * aip + c * aiq;
          a[q][i] = a[i][q];
        }
      }
      for (let i = 0; i < 3; i++) {
        const vip = v[i][p];
        const viq = v[i][q];
        v[i][p] = c * vip - s * viq;
        v[i][q] = s * vip + c * viq;
      }
    }
  }
  return { values: [a[0][0], a[1][1], a[2][2]], vectors: v };
}

function svd3(h: Mat3): { u: Mat3; v: Mat3 } {
  const hth = multiply3(transpose3(h), h);
  const { values, vectors } = jacobiEigenSymmetric3(hth);
  const order = [0, 1, 2].sort((i, j) => values[j] - values[i]);
  const v: Mat3 = zeros3();
  const singular: number[] = [];
  for (let col = 0; col < 3; col++) {
    const src = order[col];
    for (let row = 0; row < 3; row++) v[row][col] = vectors[row][src];
    singular.push(Math.sqrt(Math.max(values[src], 0)));
  }
  // u_i = H v_i / sigma_i is the real singular vector wherever sigma_i is well-defined; a
  // near-zero singular value (rank-deficient H -- e.g. a degenerate/near-planar point set) has no
  // reliable direction from that formula, so that column is instead filled in afterward as
  // whatever completes an orthonormal basis with the columns that WERE well-defined.
  const u: Mat3 = zeros3();
  const degenerate: number[] = [];
  for (let col = 0; col < 3; col++) {
    if (singular[col] > 1e-9) {
      const hv = mulVec3(h, [v[0][col], v[1][col], v[2][col]]);
      for (let row = 0; row < 3; row++) u[row][col] = hv[row] / singular[col];
    } else {
      degenerate.push(col);
    }
  }
  if (degenerate.length === 1) {
    const [missing] = degenerate;
    const others = [0, 1, 2].filter((c) => c !== missing);
    const a: Vec3 = [u[0][others[0]], u[1][others[0]], u[2][others[0]]];
    const b: Vec3 = [u[0][others[1]], u[1][others[1]], u[2][others[1]]];
    const filled = cross3(a, b);
    u[0][missing] = filled[0];
    u[1][missing] = filled[1];
    u[2][missing] = filled[2];
  } else if (degenerate.length >= 2) {
    for (let col = 0; col < 3; col++) u[col][col] = 1;
  }
  return { u, v };
}

function cross3(a: Vec3, b: Vec3): Vec3 {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}

/** Re-expresses `after` in the same rigid frame (rotation + translation) `before` was in, via
 * Kabsch/orthogonal-Procrustes alignment (mirrors convergence_checker.remove_rigid_motion). */
export function removeRigidMotion(before: Vec3[], after: Vec3[]): Vec3[] {
  const cBefore = mean(before);
  const cAfter = mean(after);
  const a = before.map((p) => sub(p, cBefore));
  const b = after.map((p) => sub(p, cAfter));
  const h: Mat3 = zeros3();
  for (let i = 0; i < a.length; i++) {
    for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) h[r][c] += b[i][r] * a[i][c];
  }
  const { u, v } = svd3(h);
  const d = Math.sign(det3(multiply3(v, transpose3(u)))) || 1;
  const diag: Mat3 = [[1, 0, 0], [0, 1, 0], [0, 0, d]];
  const r = multiply3(multiply3(v, diag), transpose3(u));
  return b.map((bi) => add(mulVec3(r, bi), cBefore));
}
