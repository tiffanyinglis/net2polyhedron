import { type BuilderConnection, type NetSpec } from "../utils/physics/mesh";
import { polygonColor, type ColorMode } from "../utils/colors";
import { type NetView } from "./editState";
import { type CameraHooks } from "./viewer";
import { drawAtlasTriangle } from "../utils/atlasDraw";

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
  private spec: NetSpec | null = null;
  /** Debug vertex labels: none, one per corner as the file names it ("raw"), or one per distinct vertex ("deduped"). */
  private vertexLabels: VertexLabelMode = "off";
  /** Right-drag pan offset in CSS pixels and wheel zoom factor; middle-click resets both. */
  private pan: [number, number] = [0, 0];
  private zoom = 1;
  private panning = false;
  private lastXY: [number, number] = [0, 0];

  /** `hooks` report the start and end of a pan, and each zoom or reset, so the owner can record undo steps. */
  /** Shown while the texture atlas loads (switching to African Flower). */
  private spinner = Object.assign(document.createElement("span"), { className: "spinner", hidden: true });

  constructor(
    private container: HTMLElement,
    private hooks: CameraHooks = {},
  ) {
    container.appendChild(this.canvas);
    container.style.position ||= "relative";
    Object.assign(this.spinner.style, {
      position: "absolute", left: "50%", top: "50%", width: "24px", height: "24px",
      margin: "-12px 0 0 -12px",
    });
    container.appendChild(this.spinner);
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
    this.spec = spec;
    this.polygons = spec ? placePolygons(spec) : [];
    this.curves = spec
      ? (spec.builder_connections ?? [])
          .map((conn) => connectionCurve(this.polygons, conn))
          .filter((curve): curve is Point[] => curve !== null)
      : [];
    this.lastColors = null;
    this.redraw();
  }

  private lastColors: { mode: ColorMode; multi: number[] } | null = null;
  /** The level-0 texture coordinates and the atlas, when the net should be drawn textured. */
  private texture: { faces: number[][]; faceOfFine: number[]; faceUV: number[][]; atlas: HTMLImageElement | HTMLCanvasElement } | null = null;

  setVertexLabels(mode: VertexLabelMode) {
    this.vertexLabels = mode;
    this.redraw();
  }

  setLoading(on: boolean) {
    this.spinner.hidden = !on;
  }

  /** Textures the net with the same wedges as the 3D mesh (level 0's per-triangle coordinates), or
   * draws it plain when `source` or `atlas` is null. */
  setTexture(source: { faces: number[][]; faceOfFine: number[]; faceUV: number[][] } | null, atlas: HTMLImageElement | HTMLCanvasElement | null) {
    this.texture = source && atlas && source.faceUV.length ? { ...source, atlas } : null;
    this.redraw();
  }

  setColors(mode: ColorMode, multiColors: number[]) {
    this.lastColors = { mode, multi: multiColors };
    this.redraw();
  }

  /**
   * Fills one net polygon with the atlas, one fine triangle at a time, each placed on the net at its own vertices.
   * False if the net isn't textured or the polygon has no triangles.
   */
  private fillTextured(ctx: CanvasRenderingContext2D, polyIndex: number, toPx: (p: Point) => Point, dpr: number): boolean {
    const tex = this.texture;
    if (!tex || !this.spec) return false;
    const triangles = tex.faceOfFine.flatMap((base, k) => (this.polygonOfBase(base) === polyIndex ? [k] : []));
    if (!triangles.length) return false;
    const placed = new Map<number, Map<number, Point>>();
    for (const k of triangles) {
      const base = tex.faceOfFine[k];
      if (!placed.has(base)) placed.set(base, this.baseCornersOnNet(base, polyIndex, toPx));
      const at = placed.get(base)!;
      const ids = tex.faces[k];
      const dst = ids.map((v) => at.get(v) ?? at.get(-1)!);
      if (dst.some((p) => !p)) continue;
      drawAtlasTriangle(ctx, tex.atlas, tex.faceUV[k], dst as Point[], dpr);
    }
    return true;
  }

  /** The polygon a base face belongs to (its net_layout index), or -1 if none. */
  private polygonOfBase(base: number): number {
    const spec = this.spec!;
    const shape = spec.source_polygon_id ? spec.source_polygon_id[base] : base;
    return this.polygons.findIndex((poly) => poly.shapeId === shape);
  }

  /**
   * Where a base face's own vertices sit on the net, keyed by mesh vertex id (-1 is the fine centroid, which
   * sits at the average of the three). A polygon's own corners follow source_polygon. A face that is one of
   * several (a split self-joined shape) takes the two of its rim vertices that are consecutive on the
   * source outline, and its remaining vertex is the polygon's centre.
   */
  private baseCornersOnNet(base: number, polyIndex: number, toPx: (p: Point) => Point): Map<number, Point> {
    const spec = this.spec!;
    const face = spec.faces[base];
    const poly = this.polygons[polyIndex];
    const outline = spec.source_polygon?.[polyIndex] ?? null;
    const corners = poly.points.map(toPx);
    const centre: Point = [
      corners.reduce((sum, p) => sum + p[0], 0) / corners.length,
      corners.reduce((sum, p) => sum + p[1], 0) / corners.length,
    ];
    const at = new Map<number, Point>();
    if (face.length === corners.length) {
      face.forEach((v, k) => at.set(v, corners[k]));
    } else if (outline) {
      const n = outline.length;
      for (let i = 0; i < face.length; i++) {
        const a = face[i];
        const b = face[(i + 1) % face.length];
        const k = outline.findIndex((v: number, idx: number) => v === a && outline[(idx + 1) % n] === b);
        const rev = outline.findIndex((v: number, idx: number) => v === b && outline[(idx + 1) % n] === a);
        if (k >= 0) {
          at.set(a, corners[k]);
          at.set(b, corners[(k + 1) % n]);
          break;
        }
        if (rev >= 0) {
          at.set(b, corners[rev]);
          at.set(a, corners[(rev + 1) % n]);
          break;
        }
      }
      for (const v of face) if (!at.has(v)) at.set(v, centre);
    }
    const average: Point = [0, 0];
    for (const v of face) {
      const p = at.get(v);
      if (p) {
        average[0] += p[0] / face.length;
        average[1] += p[1] / face.length;
      }
    }
    at.set(-1, average);
    return at;
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
    for (const [polyIndex, poly] of this.polygons.entries()) {
      const color =
        this.lastColors?.mode === "multi"
          ? (this.lastColors.multi[poly.faceIndex] ?? polygonColor(poly.sides))
          : polygonColor(poly.sides);
      ctx.beginPath();
      poly.points.map(toPx).forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      ctx.closePath();
      if (!this.fillTextured(ctx, polyIndex, toPx, dpr)) {
        ctx.globalAlpha = 0.9;
        ctx.fillStyle = hex(color);
        ctx.fill();
        ctx.globalAlpha = 1;
      }
      // The textured fill starts its own paths, so trace the polygon again before outlining it.
      ctx.beginPath();
      poly.points.map(toPx).forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      ctx.closePath();
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

    if (this.spec && this.vertexLabels !== "off") this.drawVertexLabels(ctx, toPx);
  }

  /** White id on a black disc at each corner. "raw" shows the id the file gives that corner; "deduped" shows the
   * joined vertex's id (the smallest among the corners the builder connections join), so joined corners match. */
  private drawVertexLabels(ctx: CanvasRenderingContext2D, toPx: (p: Point) => Point) {
    const spec = this.spec!;
    if (this.vertexLabels === "raw") {
      for (const poly of this.polygons) {
        cornerVertexIds(spec, poly).forEach((id, i) => drawLabel(ctx, String(id), toPx(poly.points[i])));
      }
      return;
    }
    // Every corner is labelled at its own position with its joined vertex's id, so joined corners show the same number.
    const { classOf, count } = joinedVertexClasses(this.polygons, spec.builder_connections ?? []);
    const members: number[][] = Array.from({ length: count }, () => []);
    this.polygons.forEach((poly, p) => {
      cornerVertexIds(spec, poly).forEach((id, i) => members[classOf[p][i]].push(id));
    });
    this.polygons.forEach((poly, p) => {
      poly.points.forEach((at, i) => drawLabel(ctx, String(Math.min(...members[classOf[p][i]])), toPx(at)));
    });
  }
}

/**
 * Groups every polygon corner into the vertex it is joined to: corners that a builder connection glues
 * together (the two edges' ends meet, reversed) share a class. classOf[p][i] is corner i of polygon p's class.
 */
function joinedVertexClasses(polygons: PlacedPolygon[], connections: BuilderConnection[]) {
  const offset: number[] = [];
  let total = 0;
  for (const poly of polygons) {
    offset.push(total);
    total += poly.points.length;
  }
  const parent = Array.from({ length: total }, (_, k) => k);
  const find = (k: number): number => (parent[k] === k ? k : (parent[k] = find(parent[k])));
  const union = (a: number, b: number) => {
    parent[find(a)] = find(b);
  };
  const polyOf = (shapeId: number | undefined) => polygons.findIndex((poly) => poly.shapeId === shapeId);
  for (const conn of connections) {
    const a = polyOf(conn.a_shape_id);
    const b = polyOf(conn.b_shape_id);
    if (a < 0 || b < 0) continue;
    const na = polygons[a].points.length;
    const nb = polygons[b].points.length;
    // Edge e joins corner e to corner e+1; glued edges meet end to end, so the ends cross over.
    const aEnd = (conn.a_edge + 1) % na;
    const bEnd = (conn.b_edge + 1) % nb;
    union(offset[a] + conn.a_edge, offset[b] + bEnd);
    union(offset[a] + aEnd, offset[b] + conn.b_edge);
  }
  const roots = new Map<number, number>();
  const classOf = polygons.map((poly, p) =>
    poly.points.map((_, i) => {
      const root = find(offset[p] + i);
      if (!roots.has(root)) roots.set(root, roots.size);
      return roots.get(root)!;
    }),
  );
  return { classOf, count: roots.size };
}

export type VertexLabelMode = "off" | "raw" | "deduped";

/** The mesh vertex id at each corner of a placed polygon: its face's vertex list, in corner order. */
function cornerVertexIds(spec: NetSpec, poly: PlacedPolygon): number[] {
  const faceIds = spec.source_polygon_id
    ? spec.faces.flatMap((_, f) => (spec.source_polygon_id![f] === poly.shapeId ? [f] : []))
    : [poly.faceIndex];
  const n = poly.points.length;
  if (faceIds.length === 1 && spec.faces[faceIds[0]].length === n) return spec.faces[faceIds[0]];
  // A polygon split into several faces has no single corner order, so its vertices are listed in the order they first appear.
  return [...new Set(faceIds.flatMap((f) => spec.faces[f]))].slice(0, n);
}

function drawLabel(ctx: CanvasRenderingContext2D, text: string, [x, y]: Point) {
  const radius = 9;
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fillStyle = "#000";
  ctx.fill();
  ctx.fillStyle = "#fff";
  ctx.font = "11px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, x, y);
}
