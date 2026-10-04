import * as THREE from "three";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { type Vec3 } from "../utils/physics/vec3";
import { REPULSION_STRENGTH, repulsionForce } from "../utils/physics/forces";
import { EDGE_LENGTH } from "../utils/physics/mesh";

/** [direction toward the light in camera space, intensity]: key, fill, headlight. */
const LIGHT_RIG: [[number, number, number], number][] = [
  [[0.9, 0.15, 0.1], 1.0],
  [[-0.7, -0.2, 0.7], 0.5],
  [[0, 0, 1], 2.2],
];

export interface DebugOverlays {
  faceNormals: boolean;
  vertexNormals: boolean;
  repulsiveForces: boolean;
}

// Colours and length fraction match the Python app's debug overlays (NORMAL_COLOR, etc.).
const FACE_NORMAL_COLOR = 0xffff00;
const VERTEX_NORMAL_COLOR = 0x00ffff;
const REPULSION_FORCE_COLOR = 0xff00ff;
const NORMAL_LENGTH_FRACTION = 0.5;

// White outline tracing each original (base) face's boundary: a tube per edge with a sphere at
// every joint. Widths are in CSS pixels; the tube radius is recomputed as the camera zooms, so the
// outline keeps that width on screen. The thin width is used when subdivision lines are hidden.
const OUTLINE_COLOR = 0xffffff;
const OUTLINE_WIDTH_PX = 3;
const OUTLINE_THIN_WIDTH_PX = 1.5;
const OUTLINE_RADIAL_SEGMENTS = 8;
/** How far the zoom must change (as a fraction) before the outline tubes are rebuilt at the new radius. */
const OUTLINE_REBUILD_TOLERANCE = 0.02;

function sub3(a: Vec3, b: Vec3): Vec3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function len3(v: Vec3): number {
  return Math.hypot(v[0], v[1], v[2]);
}

/** Unnormalised Newell normal of a (possibly non-triangular) face; its length is twice the area. */
function faceNormal(face: number[], pts: Vec3[]): Vec3 {
  const n: Vec3 = [0, 0, 0];
  for (let i = 0; i < face.length; i++) {
    const [x1, y1, z1] = pts[face[i]];
    const [x2, y2, z2] = pts[face[(i + 1) % face.length]];
    n[0] += (y1 - y2) * (z1 + z2);
    n[1] += (z1 - z2) * (x1 + x2);
    n[2] += (x1 - x2) * (y1 + y2);
  }
  return n;
}

function meanEdgeLength(face: number[], pts: Vec3[]): number {
  let total = 0;
  for (let i = 0; i < face.length; i++) total += len3(sub3(pts[face[i]], pts[face[(i + 1) % face.length]]));
  return total / face.length;
}

function centroid(face: number[], pts: Vec3[]): Vec3 {
  const c: Vec3 = [0, 0, 0];
  for (const v of face) for (let k = 0; k < 3; k++) c[k] += pts[v][k] / face.length;
  return c;
}

/** Outline segments: each fine triangle edge whose id is on an original polygon's outer boundary
 * (`outlineEdgeIds`, from the topology). Keyed by id, so a glued seam is drawn once. */
function outlineSegmentEnds(faces: number[][], faceEdgeIds: number[][], outlineEdgeIds: Set<number>): [number, number][] {
  const ends = new Map<number, [number, number]>();
  faces.forEach((face, f) => {
    face.forEach((a, i) => {
      const id = faceEdgeIds[f][i];
      if (outlineEdgeIds.has(id) && !ends.has(id)) ends.set(id, [a, face[(i + 1) % face.length]]);
    });
  });
  return [...ends.values()];
}

function pushSegment(out: number[], a: Vec3, b: Vec3) {
  out.push(...a, ...b);
}

function faceNormalSegments(pts: Vec3[], faces: number[][]): number[] {
  const out: number[] = [];
  for (const face of faces) {
    const n = faceNormal(face, pts);
    const nl = len3(n);
    if (nl < 1e-12) continue;
    const c = centroid(face, pts);
    const e = meanEdgeLength(face, pts) * NORMAL_LENGTH_FRACTION;
    pushSegment(out, c, [c[0] + (n[0] / nl) * e, c[1] + (n[1] / nl) * e, c[2] + (n[2] / nl) * e]);
  }
  return out;
}

/** Normalised sum of incident faces' unit normals, each face weighted equally (as the Python app's vertex_normals). */
function vertexNormalSegments(pts: Vec3[], faces: number[][]): number[] {
  const sums: Vec3[] = pts.map(() => [0, 0, 0]);
  const edgeSum = pts.map(() => 0);
  const edgeCount = pts.map(() => 0);
  for (const face of faces) {
    const n = faceNormal(face, pts);
    const nl = len3(n);
    if (nl < 1e-12) continue;
    const unit: Vec3 = [n[0] / nl, n[1] / nl, n[2] / nl];
    for (const v of face) for (let k = 0; k < 3; k++) sums[v][k] += unit[k];
    for (let i = 0; i < face.length; i++) {
      const a = face[i];
      const b = face[(i + 1) % face.length];
      const length = len3(sub3(pts[a], pts[b]));
      for (const v of [a, b]) {
        edgeSum[v] += length;
        edgeCount[v] += 1;
      }
    }
  }
  const out: number[] = [];
  pts.forEach((p, v) => {
    const s = len3(sums[v]);
    if (s < 1e-12 || edgeCount[v] === 0) return;
    const e = (edgeSum[v] / edgeCount[v]) * NORMAL_LENGTH_FRACTION;
    pushSegment(out, p, [p[0] + (sums[v][0] / s) * e, p[1] + (sums[v][1] / s) * e, p[2] + (sums[v][2] / s) * e]);
  });
  return out;
}

/** Width in CSS pixels of the 3D hover and selection outlines. */
const HIGHLIGHT_LINE_WIDTH = 4;
/** How far a highlight outline is lifted off the surface, as a fraction of the mesh's radius. */
const HIGHLIGHT_LIFT_FRACTION = 0.005;
/** Radius of an edge's tube, as a fraction of the mesh's radius. */
const EDGE_TUBE_RADIUS_FRACTION = 0.012;

/** Unit normal of a polygon (Newell's method), for any winding of its points. */
function unitNormal(points: Vec3[]): Vec3 {
  const n: Vec3 = [0, 0, 0];
  points.forEach((p, i) => {
    const q = points[(i + 1) % points.length];
    n[0] += (p[1] - q[1]) * (p[2] + q[2]);
    n[1] += (p[2] - q[2]) * (p[0] + q[0]);
    n[2] += (p[0] - q[0]) * (p[1] + q[1]);
  });
  const len = Math.hypot(n[0], n[1], n[2]) || 1;
  return [n[0] / len, n[1] / len, n[2] / len];
}

/** Arrow per repelling vertex in the repulsion force's own direction, scaled so the strongest one is a
 * reference length (matching the Python app's "relative magnitude" rule). The reference is a fixed
 * solver edge, not this mesh's own edges, so a level's arrows don't shrink as the mesh is subdivided.
 * Only the vertices in `repIndices` repel, as the solver's own repulsion does. */
function repulsionSegments(pts: Vec3[], repIndices: number[], repMultipliers: number[]): number[] {
  const forces = repulsionForce(pts, REPULSION_STRENGTH, repIndices, repMultipliers);
  const magnitudes = forces.map(len3);
  const maxLen = Math.max(0, ...magnitudes);
  if (maxLen < 1e-12) return [];
  const reference = EDGE_LENGTH * NORMAL_LENGTH_FRACTION;
  const scale = reference / maxLen;
  const out: number[] = [];
  pts.forEach((p, v) => {
    if (magnitudes[v] < 1e-12) return;
    const f = forces[v];
    pushSegment(out, p, [p[0] + f[0] * scale, p[1] + f[1] * scale, p[2] + f[2] * scale]);
  });
  return out;
}

/** A camera's full value, as plain numbers so it can be copied, compared and saved. */
export interface CameraState {
  orientation: [number, number, number, number];
  zoom: number;
  pan: [number, number];
}

/** Rotation/zoom shared by every Level panel (drag any panel -> all rotate together, as in the
 * Python app); each panel still auto-fits its own mesh's size. */
export class SharedCamera {
  orientation = new THREE.Quaternion();
  zoom = 1;
  /** Right-drag pan, in camera-screen axes and in units of each panel's own fit distance. */
  pan: [number, number] = [0, 0];

  constructor() {
    this.reset();
  }

  /** Back to the default view: starting rotation, zoom 1, no pan. */
  reset() {
    this.orientation.setFromEuler(new THREE.Euler(-0.5, 0.6, 0, "YXZ"));
    this.zoom = 1;
    this.pan = [0, 0];
  }

  snapshot(): CameraState {
    const { x, y, z, w } = this.orientation;
    return { orientation: [x, y, z, w], zoom: this.zoom, pan: [this.pan[0], this.pan[1]] };
  }

  apply(state: CameraState) {
    this.orientation.set(...state.orientation);
    this.zoom = state.zoom;
    this.pan = [state.pan[0], state.pan[1]];
  }
}

/** Notifications a Viewer gives its owner, so undo/redo can record what the camera was before a change. */
export interface CameraHooks {
  /** A drag or pan gesture is starting (before the camera moves). */
  onGestureStart?: () => void;
  /** A drag or pan gesture has ended (after its last move). */
  onGestureEnd?: () => void;
  /** A single discrete change (one wheel tick, a middle-click reset) is about to happen. */
  onBeforeDiscreteEdit?: () => void;
}

/** Minimal Three.js mesh viewer: a camera-relative key/fill/headlight rig (matching the Python
 * apps' own plotter_lighting rig), drag-to-orbit, scroll-to-zoom, auto-fit on load. No build-step-free CDN
 * dependency here since this whole webapp goes through Vite/npm -- three is a normal dependency. */
export class Viewer {
  private renderer: THREE.WebGLRenderer;
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private mesh: THREE.Mesh | null = null;
  private wireframe: THREE.LineSegments | null = null;
  private maxRadius = 1;
  private lights: { light: THREE.DirectionalLight; dir: THREE.Vector3 }[] = [];
  private dragging = false;
  private panning = false;
  private height = 1;
  private lastXY: [number, number] = [0, 0];
  private overlayFlags: DebugOverlays = { faceNormals: false, vertexNormals: false, repulsiveForces: false };
  private overlayObjects: THREE.LineSegments[] = [];
  private meshData: { pts: Vec3[]; faces: number[][] } | null = null;
  private vertexIds: number[] = [];
  /** Per triangle of the current mesh: the base face it belongs to (what pick() returns). */
  private triangleBaseFace: number[] = [];
  /** Per fine face of the current mesh: its base face. */
  private fineBaseFace: number[] = [];
  /** Highlight outlines on the current mesh (rebuilt when the mesh or the highlights change). */
  private highlightObjects: LineSegments2[] = [];
  /** Their materials, so a resize can keep the line width in pixels. */
  private highlightMaterials: LineMaterial[] = [];
  private edgeHighlightObjects: THREE.Group[] = [];
  private edgeHighlightGeometries: THREE.BufferGeometry[] = [];
  private repulsion: Map<number, number> | null = null;
  private center: Vec3 = [0, 0, 0];
  private outlineEdges: [number, number][] = [];
  private outlineObjects: THREE.InstancedMesh[] = [];
  private outlineMaterial = new THREE.MeshBasicMaterial({ color: OUTLINE_COLOR });
  private outlineTube = new THREE.CylinderGeometry(1, 1, 1, OUTLINE_RADIAL_SEGMENTS); // unit length along Y
  private outlineJoint = new THREE.SphereGeometry(1, OUTLINE_RADIAL_SEGMENTS, 6);
  /** Tube radius (world units) the outline was last built with. */
  private builtOutlineRadius = 0;
  private showOutline = true;
  private showSubdivisions = false;

  constructor(
    container: HTMLElement,
    private cam: SharedCamera,
    private onCameraChange: () => void,
    private hooks: CameraHooks = {},
  ) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    // Same as the net panel's background (--plot-bg in style.css), so every drawing area matches.
    this.scene.background = new THREE.Color(0x1c1c1c);

    this.camera = new THREE.PerspectiveCamera(45, 1, 0.01, 100);

    // Camera-relative key/fill/headlight rig, same directions as utils/inflate_polyhedron/
    // plotter_lighting.py ("camera light" space: camera at (0,0,1) looking at the origin).
    // Intensities are scaled up from the VTK values since three.js lights are dimmer per unit.
    for (const [dir, intensity] of LIGHT_RIG) {
      const light = new THREE.DirectionalLight(0xffffff, intensity);
      this.scene.add(light);
      this.lights.push({ light, dir: new THREE.Vector3(...dir) });
    }
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.4));

    this.resize(container);
    new ResizeObserver(() => this.resize(container)).observe(container);

    const canvas = this.renderer.domElement;
    canvas.addEventListener("contextmenu", (e) => e.preventDefault()); // right-drag pans, no menu
    canvas.addEventListener("pointerdown", (e) => {
      if (e.button === 1) {
        // Middle-click resets the whole shared view (rotation, zoom and pan).
        e.preventDefault();
        // Resetting an already-default view changes nothing, so it's not an undo step.
        if (!this.isDefaultView()) {
          this.hooks.onBeforeDiscreteEdit?.();
          this.cam.reset();
          this.onCameraChange();
        }
        return;
      }
      if (e.button !== 0 && e.button !== 2) return;
      this.dragging = true;
      this.panning = e.button === 2;
      this.lastXY = [e.clientX, e.clientY];
      this.hooks.onGestureStart?.();
    });
    window.addEventListener("pointerup", () => {
      if (!this.dragging) return;
      this.dragging = false;
      this.hooks.onGestureEnd?.();
    });
    window.addEventListener("pointermove", (e) => {
      if (!this.dragging) return;
      const dx = e.clientX - this.lastXY[0];
      const dy = e.clientY - this.lastXY[1];
      this.lastXY = [e.clientX, e.clientY];
      if (this.panning) {
        // One pixel is 2*tan(fov/2) of the view height at the camera's distance (fitDistance / zoom);
        // express that in fitDistance units, so the pan stays the same across panels of similar size.
        const k = (2 * Math.tan(Math.PI / 8)) / (this.cam.zoom * this.height);
        this.cam.pan = [this.cam.pan[0] - dx * k, this.cam.pan[1] + dy * k];
        this.onCameraChange();
        return;
      }
      // Rotate about the camera's own axes so the drag direction always matches the screen,
      // even after going over the poles (yaw/pitch angles flip the horizontal direction there).
      const delta = new THREE.Quaternion().setFromEuler(new THREE.Euler(-dy * 0.01, -dx * 0.01, 0));
      this.cam.orientation.multiply(delta).normalize();
      this.onCameraChange();
    });
    this.renderer.domElement.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        const zoom = Math.max(0.3, Math.min(4, this.cam.zoom * (e.deltaY > 0 ? 1 / 1.1 : 1.1)));
        // At the zoom limit a tick changes nothing, so it's not an undo step.
        if (zoom === this.cam.zoom) return;
        this.hooks.onBeforeDiscreteEdit?.();
        this.cam.zoom = zoom;
        this.onCameraChange();
      },
      { passive: false },
    );

    this.render();
  }

  /** True when the shared camera is at its starting rotation, zoom 1 and no pan. */
  private isDefaultView(): boolean {
    const d = new SharedCamera().snapshot();
    const c = this.cam.snapshot();
    return c.zoom === d.zoom && c.pan[0] === 0 && c.pan[1] === 0 &&
      c.orientation.every((v, i) => Math.abs(v - d.orientation[i]) < 1e-9);
  }

  private resize(container: HTMLElement) {
    const { clientWidth: w, clientHeight: h } = container;
    this.height = h || 1;
    this.renderer.setSize(w, h);
    this.camera.aspect = w / (h || 1);
    this.camera.updateProjectionMatrix();
    this.updateHighlightResolution();
    this.render();
  }

  /** Line materials measure their width in pixels of the drawing buffer, so they follow its size. */
  private updateHighlightResolution() {
    const { width, height } = this.renderer.domElement;
    for (const material of this.highlightMaterials) material.resolution.set(width, height);
  }

  /** `faceOfFine[i]` is the original (un-subdivided) face that `faces[i]` belongs to, and
   * `baseColors[b]` the colour of original face b. */
  /** `faceEdgeIds` parallels `faces` (edge identity, see Mesh.faceEdgeIds); `outlineEdgeIds` are the
   * ids drawn as the white polygon outline. */
  setMesh(
    faces: number[][],
    faceEdgeIds: number[][],
    positions: Map<number, Vec3>,
    faceOfFine: number[],
    baseColors: number[],
    outlineEdgeIds: Set<number>,
  ) {
    if (this.mesh) {
      this.scene.remove(this.mesh);
      this.mesh.geometry.dispose();
      for (const m of this.mesh.material as THREE.Material[]) m.dispose();
    }
    if (this.wireframe) {
      this.scene.remove(this.wireframe);
      this.wireframe.geometry.dispose();
      (this.wireframe.material as THREE.Material).dispose();
    }

    const vertexIds = [...positions.keys()];
    const idx = new Map(vertexIds.map((v, i) => [v, i]));
    const vertexArray = new Float32Array(vertexIds.length * 3);
    let center: Vec3 = [0, 0, 0];
    for (const v of vertexIds) {
      const p = positions.get(v)!;
      center = [center[0] + p[0], center[1] + p[1], center[2] + p[2]];
    }
    center = center.map((c) => c / vertexIds.length) as Vec3;
    this.center = center;
    this.vertexIds = vertexIds;
    let maxRadius = 0;
    vertexIds.forEach((v, i) => {
      const p = positions.get(v)!;
      const cx = p[0] - center[0];
      const cy = p[1] - center[1];
      const cz = p[2] - center[2];
      vertexArray[i * 3] = cx;
      vertexArray[i * 3 + 1] = cy;
      vertexArray[i * 3 + 2] = cz;
      maxRadius = Math.max(maxRadius, Math.hypot(cx, cy, cz));
    });

    // Triangles are emitted grouped by original face, one geometry group (= one material) each.
    const indexArray: number[] = [];
    const geometry = new THREE.BufferGeometry();
    this.triangleBaseFace = [];
    this.fineBaseFace = faceOfFine.slice();
    baseColors.forEach((_, b) => {
      const start = indexArray.length;
      faces.forEach((face, f) => {
        if (faceOfFine[f] !== b) return;
        for (let i = 1; i < face.length - 1; i++) {
          indexArray.push(idx.get(face[0])!, idx.get(face[i])!, idx.get(face[i + 1])!);
          this.triangleBaseFace.push(b);
        }
      });
      geometry.addGroup(start, indexArray.length - start, b);
    });
    geometry.setAttribute("position", new THREE.BufferAttribute(vertexArray, 3));
    geometry.setIndex(indexArray);

    // Phong, like the Python app (specular 0.5, power 20, smooth_shading=False): flatShading
    // lights each triangle by its own face normal instead of the averaged per-vertex normals,
    // which blur neighbouring triangles together into one smooth blob.
    const materials = baseColors.map(
      (color) =>
        new THREE.MeshPhongMaterial({
          color,
          specular: 0x808080,
          shininess: 20,
          flatShading: true,
          side: THREE.DoubleSide,
        }),
    );
    this.mesh = new THREE.Mesh(geometry, materials);
    this.scene.add(this.mesh);

    const wireGeometry = new THREE.WireframeGeometry(geometry);
    this.wireframe = new THREE.LineSegments(
      wireGeometry,
      new THREE.LineBasicMaterial({ color: 0xffffff, opacity: 0.25, transparent: true }),
    );
    this.wireframe.visible = this.showSubdivisions;
    this.scene.add(this.wireframe);

    this.maxRadius = maxRadius;
    this.meshData = {
      pts: vertexIds.map((_, i) => [vertexArray[i * 3], vertexArray[i * 3 + 1], vertexArray[i * 3 + 2]] as Vec3),
      faces: faces.map((face) => face.map((v) => idx.get(v)!)),
    };
    this.outlineEdges = outlineSegmentEnds(this.meshData.faces, faceEdgeIds, outlineEdgeIds);
    this.rebuildOutline();
    this.rebuildOverlays();
    this.render();
  }

  /** Empties the panel (a level that hasn't been computed yet). */
  clear() {
    for (const obj of [this.mesh, this.wireframe]) {
      if (!obj) continue;
      this.scene.remove(obj);
      obj.geometry.dispose();
    }
    this.mesh = null;
    this.wireframe = null;
    this.meshData = null;
    this.outlineEdges = [];
    this.rebuildOutline();
    this.rebuildOverlays();
    this.render();
  }

  /** Shows another set of positions for the current mesh (a replay frame) without refitting the camera. */
  showPositions(positions: Map<number, Vec3>) {
    if (!this.mesh || !this.meshData) return;
    const pts = this.vertexIds.map((v) => {
      const p = positions.get(v)!;
      return [p[0] - this.center[0], p[1] - this.center[1], p[2] - this.center[2]] as Vec3;
    });
    const attr = this.mesh.geometry.getAttribute("position") as THREE.BufferAttribute;
    pts.forEach((p, i) => attr.setXYZ(i, p[0], p[1], p[2]));
    attr.needsUpdate = true;
    this.wireframe!.geometry.dispose();
    this.wireframe!.geometry = new THREE.WireframeGeometry(this.mesh.geometry);
    this.meshData.pts = pts;
    this.rebuildOutline();
    this.rebuildOverlays();
    this.render();
  }

  /** Shows or hides the base-face outline and the subdivision (fine triangle) wireframe. */
  setLayers(outline: boolean, subdivisions: boolean) {
    this.showOutline = outline;
    this.showSubdivisions = subdivisions;
    this.rebuildOutline(); // the width depends on whether subdivisions are shown too
    if (this.wireframe) this.wireframe.visible = subdivisions;
    this.render();
  }

  /**
   * The vertices that repel, with their multipliers, as the solver applies them at the level on screen
   * (repulsionMultipliers). Null: no overlay of repulsive forces.
   */
  setRepulsion(multipliers: Map<number, number> | null) {
    this.repulsion = multipliers;
    this.rebuildOverlays();
    this.render();
  }

  /** The repelling vertices' indices in the current mesh, and their multipliers. */
  private repulsionIndices(): { indices: number[]; multipliers: number[] } {
    const indices: number[] = [];
    const multipliers: number[] = [];
    this.vertexIds.forEach((v, i) => {
      const m = this.repulsion?.get(v);
      if (m !== undefined) {
        indices.push(i);
        multipliers.push(m);
      }
    });
    return { indices, multipliers };
  }

  setOverlays(flags: DebugOverlays) {
    this.overlayFlags = flags;
    this.rebuildOverlays();
    this.render();
  }

  /** Tube radius, in world units, that makes the outline `OUTLINE_WIDTH_PX` (or the thin width) wide on screen at the current zoom. */
  private outlineWorldRadius(): number {
    // Same camera distance and 45° field of view as render(): one pixel spans this many world units.
    const distance = this.fitDistance() / this.cam.zoom;
    const worldPerPixel = (2 * distance * Math.tan(Math.PI / 8)) / this.height;
    const widthPx = this.showSubdivisions ? OUTLINE_WIDTH_PX : OUTLINE_THIN_WIDTH_PX;
    return (worldPerPixel * widthPx) / 2;
  }

  /** Rebuilds the base-face outline at the current positions and the current zoom (tubes + joint spheres as instanced meshes). */
  private rebuildOutline() {
    for (const obj of this.outlineObjects) {
      this.scene.remove(obj);
      obj.dispose();
    }
    this.outlineObjects = [];
    if (!this.meshData || !this.outlineEdges.length) return;

    const { pts } = this.meshData;
    const radius = this.outlineWorldRadius();
    this.builtOutlineRadius = radius;
    const up = new THREE.Vector3(0, 1, 0);
    const tubeMatrices: THREE.Matrix4[] = [];
    const jointIds = new Set<number>();
    for (const [a, b] of this.outlineEdges) {
      const start = new THREE.Vector3(...pts[a]);
      const end = new THREE.Vector3(...pts[b]);
      const dir = end.clone().sub(start);
      const length = dir.length();
      if (length < 1e-12) continue;
      const rotation = new THREE.Quaternion().setFromUnitVectors(up, dir.divideScalar(length));
      const midpoint = start.add(end).multiplyScalar(0.5);
      tubeMatrices.push(
        new THREE.Matrix4().compose(midpoint, rotation, new THREE.Vector3(radius, length, radius)),
      );
      jointIds.add(a);
      jointIds.add(b);
    }
    const jointMatrices = [...jointIds].map((v) =>
      new THREE.Matrix4().compose(
        new THREE.Vector3(...pts[v]),
        new THREE.Quaternion(),
        new THREE.Vector3(radius, radius, radius),
      ),
    );
    this.addOutlineInstances(this.outlineTube, tubeMatrices);
    this.addOutlineInstances(this.outlineJoint, jointMatrices);
  }

  private addOutlineInstances(geometry: THREE.BufferGeometry, matrices: THREE.Matrix4[]) {
    if (!matrices.length) return;
    const instances = new THREE.InstancedMesh(geometry, this.outlineMaterial, matrices.length);
    instances.visible = this.showOutline;
    matrices.forEach((m, i) => instances.setMatrixAt(i, m));
    instances.instanceMatrix.needsUpdate = true;
    this.scene.add(instances);
    this.outlineObjects.push(instances);
  }

  private rebuildOverlays() {
    for (const line of this.overlayObjects) {
      this.scene.remove(line);
      line.geometry.dispose();
      (line.material as THREE.Material).dispose();
    }
    this.overlayObjects = [];
    if (!this.meshData) return;
    const { pts, faces } = this.meshData;
    const { faceNormals, vertexNormals, repulsiveForces } = this.overlayFlags;
    if (faceNormals) this.addOverlay(faceNormalSegments(pts, faces), FACE_NORMAL_COLOR);
    if (vertexNormals) this.addOverlay(vertexNormalSegments(pts, faces), VERTEX_NORMAL_COLOR);
    if (repulsiveForces && this.repulsion) {
      const { indices, multipliers } = this.repulsionIndices();
      this.addOverlay(repulsionSegments(pts, indices, multipliers), REPULSION_FORCE_COLOR);
    }
  }

  private addOverlay(segments: number[], color: number) {
    if (!segments.length) return;
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(segments, 3));
    const line = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ color }));
    this.scene.add(line);
    this.overlayObjects.push(line);
  }

  /** Screen distance in CSS px from a client point to the segment a-b (both in the coordinates given to setMesh). */
  edgeDistance(clientX: number, clientY: number, a: Vec3, b: Vec3): number {
    const rect = this.renderer.domElement.getBoundingClientRect();
    const sa = this.toClient(a, rect);
    const sb = this.toClient(b, rect);
    const [px, py] = [clientX, clientY];
    const [dx, dy] = [sb[0] - sa[0], sb[1] - sa[1]];
    const len2 = dx * dx + dy * dy;
    const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - sa[0]) * dx + (py - sa[1]) * dy) / len2));
    return Math.hypot(px - (sa[0] + t * dx), py - (sa[1] + t * dy));
  }

  /** True if nothing of the mesh hides point p (setMesh's coordinates) from the camera. */
  isVisible(p: Vec3): boolean {
    if (!this.mesh) return false;
    const target = new THREE.Vector3(p[0] - this.center[0], p[1] - this.center[1], p[2] - this.center[2]);
    const origin = this.camera.position.clone();
    const dist = origin.distanceTo(target);
    const dir = target.clone().sub(origin).normalize();
    const hit = new THREE.Raycaster(origin, dir).intersectObject(this.mesh)[0];
    // A silhouette edge is nearly tangent to the view, so the surface can sit a fair way in front of it
    // along the ray (about a fifth of the radius on a tetrahedron). A back edge is behind the body's
    // whole thickness, which is much more, so half a radius separates the two.
    return !hit || hit.distance >= dist - this.maxRadius * 0.5;
  }

  /** Client coordinates of a point given in setMesh's coordinates. */
  private toClient(p: Vec3, rect: DOMRect): [number, number] {
    const v = new THREE.Vector3(p[0] - this.center[0], p[1] - this.center[1], p[2] - this.center[2]).project(this.camera);
    return [rect.left + ((v.x + 1) / 2) * rect.width, rect.top + ((1 - v.y) / 2) * rect.height];
  }

  /**
   * Draws each edge path (points in setMesh's coordinates) as a tube of real 3D geometry: a cylinder per
   * segment with a sphere at every joint and end, so the joins and caps are round. The tube is lifted
   * toward the camera by its own radius so it sits in front of the surface it runs along, and the depth
   * test hides whichever part is behind the surface.
   */
  setEdgeHighlights(paths: { path: Vec3[]; color: number }[]) {
    for (const group of this.edgeHighlightObjects) this.scene.remove(group);
    for (const geometry of this.edgeHighlightGeometries) geometry.dispose();
    this.edgeHighlightObjects = [];
    this.edgeHighlightGeometries = [];
    const radius = this.maxRadius * EDGE_TUBE_RADIUS_FRACTION;
    const sphere = new THREE.SphereGeometry(radius, 10, 8);
    const tube = new THREE.CylinderGeometry(radius, radius, 1, 10, 1, false);
    this.edgeHighlightGeometries.push(sphere, tube);
    const c = this.camera.position;
    const toward = (p: Vec3): THREE.Vector3 => {
      const q = new THREE.Vector3(p[0] - this.center[0], p[1] - this.center[1], p[2] - this.center[2]);
      return q.add(c.clone().sub(q).normalize().multiplyScalar(radius));
    };
    for (const { path, color } of paths) {
      if (path.length < 2) continue;
      const material = new THREE.MeshBasicMaterial({ color });
      const group = new THREE.Group();
      const points = path.map(toward);
      for (const p of points) {
        const m = new THREE.Mesh(sphere, material);
        m.position.copy(p);
        group.add(m);
      }
      for (let i = 0; i + 1 < points.length; i++) {
        const a = points[i];
        const b = points[i + 1];
        const len = a.distanceTo(b);
        if (len < 1e-12) continue;
        const m = new THREE.Mesh(tube, material);
        m.position.copy(a).add(b).multiplyScalar(0.5);
        m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.clone().sub(a).normalize());
        m.scale.set(1, len, 1);
        group.add(m);
      }
      this.scene.add(group);
      this.edgeHighlightObjects.push(group);
    }
    this.render();
  }

  /** The base face under a screen point (client coordinates), or null if the pointer isn't over the mesh. */
  pick(clientX: number, clientY: number): number | null {
    if (!this.mesh) return null;
    const rect = this.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(((clientX - rect.left) / rect.width) * 2 - 1, -((clientY - rect.top) / rect.height) * 2 + 1);
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(ndc, this.camera);
    const hit = raycaster.intersectObject(this.mesh)[0];
    if (!hit || hit.faceIndex == null) return null;
    return this.triangleBaseFace[hit.faceIndex] ?? null;
  }

  /**
   * Outlines the region covered by each layer's base faces, in that layer's colour, on top of the mesh.
   * A region's outline is the edges its own fine triangles share with a triangle outside it.
   */
  setHighlights(layers: { baseFaces: Set<number>; color: number }[]) {
    for (const obj of this.highlightObjects) {
      this.scene.remove(obj);
      obj.geometry.dispose();
    }
    for (const material of this.highlightMaterials) material.dispose();
    this.highlightObjects = [];
    this.highlightMaterials = [];
    if (!this.meshData) return;
    const { pts, faces } = this.meshData;
    for (const { baseFaces, color } of layers) {
      if (baseFaces.size === 0) continue;
      const inside = faces.map((_, f) => baseFaces.has(this.fineBaseFace[f]));
      const edgeCount = new Map<string, { a: number; b: number; n: number; normal: Vec3 }>();
      faces.forEach((face, f) => {
        if (!inside[f]) return;
        const normal = unitNormal(face.map((v) => pts[v]));
        face.forEach((a, i) => {
          const b = face[(i + 1) % face.length];
          const key = a < b ? `${a},${b}` : `${b},${a}`;
          const entry = edgeCount.get(key);
          if (entry) entry.n += 1;
          else edgeCount.set(key, { a, b, n: 1, normal });
        });
      });
      // The outline is real 3D geometry, depth-tested, so the surface hides whatever is behind it. It's
      // lifted a little off the surface along its own face's normal, so it doesn't fight the faces for depth.
      const lift = this.maxRadius * HIGHLIGHT_LIFT_FRACTION;
      const segments: number[] = [];
      for (const { a, b, n, normal } of edgeCount.values()) {
        if (n !== 1) continue;
        const up = (p: Vec3): Vec3 => [p[0] + normal[0] * lift, p[1] + normal[1] * lift, p[2] + normal[2] * lift];
        pushSegment(segments, up(pts[a]), up(pts[b]));
      }
      if (!segments.length) continue;
      // WebGL draws plain lines one pixel wide, so the highlight is a fat line measured in device pixels.
      const geometry = new LineSegmentsGeometry().setPositions(segments);
      const material = new LineMaterial({
        color,
        linewidth: HIGHLIGHT_LINE_WIDTH * this.renderer.getPixelRatio(),
        depthTest: true,
      });
      this.highlightMaterials.push(material);
      const line = new LineSegments2(geometry, material);
      this.scene.add(line);
      this.highlightObjects.push(line);
    }
    this.updateHighlightResolution();
    this.render();
  }

  /** Recolours the current mesh in place (one colour per original face) without refitting the camera. */
  setBaseColors(baseColors: number[]) {
    if (!this.mesh) return;
    (this.mesh.material as THREE.MeshPhongMaterial[]).forEach((m, b) => m.color.set(baseColors[b]));
    this.render();
  }

  /** Distance that fits the mesh's bounding sphere, widened for a panel narrower than tall. */
  private fitDistance(): number {
    return (Math.max(1, this.maxRadius * 2.6)) / Math.min(1, this.camera.aspect);
  }

  render() {
    // The outline's pixel width needs a new tube radius whenever the zoom (or the panel's height) changes.
    if (this.outlineEdges.length) {
      const radius = this.outlineWorldRadius();
      if (Math.abs(radius - this.builtOutlineRadius) > OUTLINE_REBUILD_TOLERANCE * this.builtOutlineRadius) {
        this.rebuildOutline();
      }
    }
    const orientation = this.cam.orientation;
    this.camera.quaternion.copy(orientation);
    const fit = this.fitDistance();
    const [panX, panY] = this.cam.pan;
    this.camera.position.set(panX * fit, panY * fit, fit / this.cam.zoom).applyQuaternion(orientation);
    // Directional lights (aimed at the origin) follow the camera's orientation.
    for (const { light, dir } of this.lights) {
      light.position.copy(dir).normalize().multiplyScalar(10).applyQuaternion(orientation);
    }
    this.renderer.render(this.scene, this.camera);
  }
}
