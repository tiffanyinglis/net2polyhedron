import * as THREE from "three";
import { type Vec3 } from "./physics/vec3";

/** [direction toward the light in camera space, intensity]: key, fill, headlight. */
const LIGHT_RIG: [[number, number, number], number][] = [
  [[0.9, 0.15, 0.1], 1.0],
  [[-0.7, -0.2, 0.7], 0.5],
  [[0, 0, 1], 2.2],
];

/** Minimal Three.js mesh viewer: a camera-relative key/fill/headlight rig (matching the Python
 * apps' own plotter_lighting rig), drag-to-orbit, scroll-to-zoom, auto-fit on load. No build-step-free CDN
 * dependency here since this whole webapp goes through Vite/npm -- three is a normal dependency. */
export class Viewer {
  private renderer: THREE.WebGLRenderer;
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private mesh: THREE.Mesh | null = null;
  private wireframe: THREE.LineSegments | null = null;
  private orientation = new THREE.Quaternion().setFromEuler(new THREE.Euler(-0.5, 0.6, 0, "YXZ"));
  private distance = 4;
  private lights: { light: THREE.DirectionalLight; dir: THREE.Vector3 }[] = [];
  private dragging = false;
  private lastXY: [number, number] = [0, 0];

  constructor(container: HTMLElement) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x1b1d22);

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

    this.renderer.domElement.addEventListener("pointerdown", (e) => {
      this.dragging = true;
      this.lastXY = [e.clientX, e.clientY];
    });
    window.addEventListener("pointerup", () => (this.dragging = false));
    window.addEventListener("pointermove", (e) => {
      if (!this.dragging) return;
      const dx = e.clientX - this.lastXY[0];
      const dy = e.clientY - this.lastXY[1];
      this.lastXY = [e.clientX, e.clientY];
      // Rotate about the camera's own axes so the drag direction always matches the screen,
      // even after going over the poles (yaw/pitch angles flip the horizontal direction there).
      const delta = new THREE.Quaternion().setFromEuler(new THREE.Euler(-dy * 0.01, -dx * 0.01, 0));
      this.orientation.multiply(delta).normalize();
      this.render();
    });
    this.renderer.domElement.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        this.distance *= e.deltaY > 0 ? 1.1 : 0.9;
        this.distance = Math.max(0.5, Math.min(50, this.distance));
        this.render();
      },
      { passive: false },
    );

    this.render();
  }

  private resize(container: HTMLElement) {
    const { clientWidth: w, clientHeight: h } = container;
    this.renderer.setSize(w, h);
    this.camera.aspect = w / (h || 1);
    this.camera.updateProjectionMatrix();
    this.render();
  }

  /** `faceOfFine[i]` is the original (un-subdivided) face that `faces[i]` belongs to, and
   * `baseColors[b]` the colour of original face b. */
  setMesh(faces: number[][], positions: Map<number, Vec3>, faceOfFine: number[], baseColors: number[]) {
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
    baseColors.forEach((_, b) => {
      const start = indexArray.length;
      faces.forEach((face, f) => {
        if (faceOfFine[f] !== b) return;
        for (let i = 1; i < face.length - 1; i++) {
          indexArray.push(idx.get(face[0])!, idx.get(face[i])!, idx.get(face[i + 1])!);
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
    this.scene.add(this.wireframe);

    this.distance = Math.max(1, maxRadius * 2.6);
    this.render();
  }

  private render() {
    this.camera.quaternion.copy(this.orientation);
    this.camera.position.set(0, 0, this.distance).applyQuaternion(this.orientation);
    // Directional lights (aimed at the origin) follow the camera's orientation.
    for (const { light, dir } of this.lights) {
      light.position.copy(dir).normalize().multiplyScalar(10).applyQuaternion(this.orientation);
    }
    this.renderer.render(this.scene, this.camera);
  }
}
