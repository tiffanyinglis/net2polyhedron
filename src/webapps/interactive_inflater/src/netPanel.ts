import { type BuilderConnection, type NetSpec } from "./physics/mesh";
import { polygonColor } from "./colors";
import { type NetView } from "./editState";
import { type CameraHooks } from "./viewer";

/** Builder canvas edge length in pixels (net_layout's cx/cy and connection handles are in these units). */
const BUILDER_EDGE_LENGTH = 70;
const BEZIER_STEPS = 24;
const CONNECTION_CURVE_COLOR = "#fff";
const CONNECTION_CURVE_WIDTH = 1.5;

type Point = [number, number];
interface PlacedPolygon {
  /** net_layout's shape_id (or the entry's position for a legacy net), keys connections. */
  shapeId: number;
  points: Point[];
  sides: number;
  /** Index of the base face whose colour this polygon takes. */
  faceIndex: number;
}

/** CCW regular k-gon, unit edge, edge 0 running vertex 0 -> 1 (mirrors geometry.polygon_geom). */
function regularPolygon(k: number): Point[] {
  const radius = 1 / (2 * Math.sin(Math.PI / k));
  const start = -Math.PI / 2 - Math.PI / k;
  return Array.from({ length: k }, (_, i) => {
    const a = start + (2 * Math.PI * i) / k;
    return [radius * Math.cos(a), radius * Math.sin(a)] as Point;
  });
}

/** Flat undeformed layout from the net's saved `net_layout` (mirrors layout_from_net_layout,
 * including the Y flip). Empty if the net has none. */
function placePolygons(spec: NetSpec): PlacedPolygon[] {
  return (spec.net_layout ?? []).map((entry, i) => {
    const sides = entry.n ?? spec.faces[i]?.length ?? 3;
    const [c, s] = [Math.cos(entry.rotation), Math.sin(entry.rotation)];
    const tx = entry.cx / BUILDER_EDGE_LENGTH;
    const ty = entry.cy / BUILDER_EDGE_LENGTH;
    const points = regularPolygon(sides).map(
      ([x, y]) => [c * x - s * y + tx, -(s * x + c * y + ty)] as Point,
    );
    const faceIndex =
      entry.shape_id !== undefined && spec.source_polygon_id
        ? Math.max(0, spec.source_polygon_id.indexOf(entry.shape_id))
        : i;
    return { shapeId: entry.shape_id ?? i, points, sides, faceIndex };
  });
}

/** Midpoint, unit tangent, and outward unit normal of one placed polygon edge (mirrors
 * geometry.placed_edge_frame; the outward test is chirality-agnostic). */
function placedEdgeFrame(points: Point[], edge: number) {
  const n = points.length;
  const [x1, y1] = points[edge];
  const [x2, y2] = points[(edge + 1) % n];
  const ox = (x1 + x2) / 2;
  const oy = (y1 + y2) / 2;
  const len = Math.hypot(x2 - x1, y2 - y1) || 1;
  const tx = (x2 - x1) / len;
  const ty = (y2 - y1) / len;
  let nx = -ty;
  let ny = tx;
  const cx = points.reduce((sum, p) => sum + p[0], 0) / n;
  const cy = points.reduce((sum, p) => sum + p[1], 0) / n;
  if ((ox - cx) * nx + (oy - cy) * ny < 0) {
    nx = -nx;
    ny = -ny;
  }
  return { mid: [ox, oy] as Point, tan: [tx, ty] as Point, norm: [nx, ny] as Point };
}

/** Sampled cubic bezier for one saved builder connection, in the same unit-edge space as the
 * polygons (mirrors geometry.connection_curve_points). Null if either shape is missing. */
function connectionCurve(polygons: PlacedPolygon[], conn: BuilderConnection): Point[] | null {
  const aKey = conn.a_shape_id ?? conn.a_face;
  const bKey = conn.b_shape_id ?? conn.b_face;
  const a = polygons.find((p) => p.shapeId === aKey);
  const b = polygons.find((p) => p.shapeId === bKey);
  if (!a || !b) return null;
  const fa = placedEdgeFrame(a.points, conn.a_edge);
  const fb = placedEdgeFrame(b.points, conn.b_edge);
  const control = (f: ReturnType<typeof placedEdgeFrame>, h = { t: 0, n: 0 }): Point => [
    f.mid[0] + (h.t / BUILDER_EDGE_LENGTH) * f.tan[0] + (h.n / BUILDER_EDGE_LENGTH) * f.norm[0],
    f.mid[1] + (h.t / BUILDER_EDGE_LENGTH) * f.tan[1] + (h.n / BUILDER_EDGE_LENGTH) * f.norm[1],
  ];
  const p0 = fa.mid;
  const p1 = control(fa, conn.a_handle);
  const p2 = control(fb, conn.b_handle);
  const p3 = fb.mid;
  return Array.from({ length: BEZIER_STEPS + 1 }, (_, i) => {
    const t = i / BEZIER_STEPS;
    const u = 1 - t;
    const w = [u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t];
    return [0, 1].map((k) => w[0] * p0[k] + w[1] * p1[k] + w[2] * p2[k] + w[3] * p3[k]) as Point;
  });
}

const hex = (c: number) => `#${c.toString(16).padStart(6, "0")}`;

/** The "Net" panel: the flat, undeformed layout with the builder's saved bezier connections
 * drawn over it (read-only -- handles are never shown). */
export class NetPanel {
  private canvas = document.createElement("canvas");
  private polygons: PlacedPolygon[] = [];
  private curves: Point[][] = [];
  /** Right-drag pan offset in CSS pixels and wheel zoom factor; middle-click resets both. */
  private pan: [number, number] = [0, 0];
  private zoom = 1;
  private panning = false;
  private lastXY: [number, number] = [0, 0];

  /** `hooks` report the start and end of a pan, and each zoom or reset, so the owner can record undo steps. */
  constructor(
    private container: HTMLElement,
    private hooks: CameraHooks = {},
  ) {
    container.appendChild(this.canvas);
    new ResizeObserver(() => this.redraw()).observe(container);
    this.canvas.addEventListener("contextmenu", (e) => e.preventDefault()); // right-drag pans, no menu
    this.canvas.addEventListener("pointerdown", (e) => {
      if (e.button === 1) {
        e.preventDefault();
        if (this.pan[0] !== 0 || this.pan[1] !== 0 || this.zoom !== 1) {
          this.hooks.onBeforeDiscreteEdit?.();
          this.pan = [0, 0];
          this.zoom = 1;
          this.redraw();
        }
      } else if (e.button === 2) {
        this.panning = true;
        this.lastXY = [e.clientX, e.clientY];
        this.canvas.setPointerCapture(e.pointerId);
        this.hooks.onGestureStart?.();
      }
    });
    this.canvas.addEventListener("pointermove", (e) => {
      if (!this.panning) return;
      this.pan = [this.pan[0] + e.clientX - this.lastXY[0], this.pan[1] + e.clientY - this.lastXY[1]];
      this.lastXY = [e.clientX, e.clientY];
      this.redraw();
    });
    this.canvas.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        const zoom = Math.max(0.2, Math.min(8, this.zoom * (e.deltaY > 0 ? 1 / 1.1 : 1.1)));
        if (zoom === this.zoom) return; // at the limit a tick changes nothing
        this.hooks.onBeforeDiscreteEdit?.();
        this.zoom = zoom;
        this.redraw();
      },
      { passive: false },
    );
    const endPan = () => {
      if (!this.panning) return;
      this.panning = false;
      this.hooks.onGestureEnd?.();
    };
    this.canvas.addEventListener("pointerup", endPan);
    this.canvas.addEventListener("pointercancel", endPan);
  }

  /** The current pan and zoom, for undo/redo. */
  view(): NetView {
    return { pan: [this.pan[0], this.pan[1]], zoom: this.zoom };
  }

  setView(view: NetView) {
    this.pan = [view.pan[0], view.pan[1]];
    this.zoom = view.zoom;
    this.redraw();
  }

  setNet(spec: NetSpec | null) {
    this.polygons = spec ? placePolygons(spec) : [];
    this.curves = spec
      ? (spec.builder_connections ?? [])
          .map((conn) => connectionCurve(this.polygons, conn))
          .filter((curve): curve is Point[] => curve !== null)
      : [];
    this.lastColors = null;
    this.redraw();
  }

  private lastColors: { mode: "polygon" | "multi"; multi: number[] } | null = null;

  setColors(mode: "polygon" | "multi", multiColors: number[]) {
    this.lastColors = { mode, multi: multiColors };
    this.redraw();
  }

  private redraw() {
    const { clientWidth: w, clientHeight: h } = this.container;
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = w * dpr;
    this.canvas.height = h * dpr;
    this.canvas.style.width = `${w}px`;
    this.canvas.style.height = `${h}px`;
    const ctx = this.canvas.getContext("2d")!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (!this.polygons.length) return;

    // Curves join the bounding box so a bulging handle can't get clipped at the panel edge.
    const all = [...this.polygons.flatMap((p) => p.points), ...this.curves.flat()];
    const xs = all.map((p) => p[0]);
    const ys = all.map((p) => p[1]);
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const pad = 0.6;
    const scale = Math.min(w / (x1 - x0 + 2 * pad), h / (y1 - y0 + 2 * pad));
    const drawScale = scale * this.zoom;
    const toPx = ([x, y]: Point): Point => [
      w / 2 + (x - (x0 + x1) / 2) * drawScale + this.pan[0],
      h / 2 + (y - (y0 + y1) / 2) * drawScale + this.pan[1],
    ];

    ctx.lineJoin = "round";
    for (const poly of this.polygons) {
      const color =
        this.lastColors?.mode === "multi"
          ? (this.lastColors.multi[poly.faceIndex] ?? polygonColor(poly.sides))
          : polygonColor(poly.sides);
      ctx.beginPath();
      poly.points.map(toPx).forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      ctx.closePath();
      ctx.globalAlpha = 0.9;
      ctx.fillStyle = hex(color);
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.strokeStyle = "#000";
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    ctx.strokeStyle = CONNECTION_CURVE_COLOR;
    ctx.lineWidth = CONNECTION_CURVE_WIDTH;
    ctx.lineCap = "round";
    for (const curve of this.curves) {
      ctx.beginPath();
      curve.map(toPx).forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      ctx.stroke();
    }
  }
}
