import { type NetSpec } from "./physics/mesh";
import { polygonColor } from "./colors";

/** Builder canvas edge length in pixels (net_layout's cx/cy are in these units). */
const BUILDER_EDGE_LENGTH = 70;

type Point = [number, number];
interface PlacedPolygon {
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
    return { points, sides, faceIndex };
  });
}

const hex = (c: number) => `#${c.toString(16).padStart(6, "0")}`;

/** The "Net" panel: the flat, undeformed layout, read-only (no connection curves yet). */
export class NetPanel {
  private canvas = document.createElement("canvas");
  private polygons: PlacedPolygon[] = [];

  constructor(private container: HTMLElement) {
    container.appendChild(this.canvas);
    new ResizeObserver(() => this.redraw()).observe(container);
  }

  setNet(spec: NetSpec | null) {
    this.polygons = spec ? placePolygons(spec) : [];
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

    const all = this.polygons.flatMap((p) => p.points);
    const xs = all.map((p) => p[0]);
    const ys = all.map((p) => p[1]);
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const pad = 0.6;
    const scale = Math.min(w / (x1 - x0 + 2 * pad), h / (y1 - y0 + 2 * pad));
    const toPx = ([x, y]: Point): Point => [
      w / 2 + (x - (x0 + x1) / 2) * scale,
      h / 2 + (y - (y0 + y1) / 2) * scale,
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
  }
}
