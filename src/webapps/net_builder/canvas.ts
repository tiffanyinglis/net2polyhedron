import { type Builder } from "./builder";
import { faceInfo, type FaceInfo, type FaceRole } from "./faceTypes";
import { type Point } from "../utils/geometry";
import { connectionGeometry, distanceToSegment, edgeMidpoints, sampleCubic, type Connection, type End } from "./joins";
import { DEFAULT_SHAPE_EDGE_LENGTH, shapeCssColor, shapeVertices, type Shape } from "./shapes";
import { edgeGroup } from "./joins";

/**
 * An equilateral triangle centred on (cx, cy), vertices at radius `r`, pointing up unless `turn` rotates it
 * (Math.PI points it down). Adds to the current path.
 */
function trianglePath(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number, turn = 0) {
  for (let i = 0; i < 3; i++) {
    const angle = -Math.PI / 2 + turn + (i * 2 * Math.PI) / 3;
    const x = cx + r * Math.cos(angle);
    const y = cy + r * Math.sin(angle);
    if (i) ctx.lineTo(x, y);
    else ctx.moveTo(x, y);
  }
  ctx.closePath();
}

const ZOOM_STEP = 1.1;
const ZOOM_MIN = 0.2;
const ZOOM_MAX = 5;
const SELECTION_COLOR = "red";
const OUTER_OUTLINE_COLOR = "white";
const OUTER_OUTLINE_WIDTH = 1.5;
const HATCH_SPACING = 10;
const HATCH_WIDTH = 2;
const CONNECTION_COLOR = "#b0b0b0";
const CONNECTION_WIDTH = 1.5;
const CONNECTION_SELECTED_WIDTH = 2.5;
/** Outline of the piece under the pointer, in either view (matches the 3D hover highlight). */
const HOVER_COLOR = "#ffd400";
/** How close (CSS px) a pointer must be to a polygon line to count as on that edge. */
const EDGE_LINE_HIT_RADIUS = 6;
const HANDLE_COLOR = "white";
/** An unreachable piece is drawn at this opacity, as the Python app's orphaned pieces are. */
const UNREACHABLE_OPACITY = 0.5;
/** Debug-mode face marks: outer radius of the star and the triangle, 1.5x the old 8px mark. */
const MARK_RADIUS = 12;
/** Edge circles and face marks smaller than this (screen px radius) aren't drawn at all. */
const MIN_DRAWN_RADIUS = 1.5;
/** Edge circles in combined mode, where they're always filled: a bit smaller than the net_builder's rings. */
const COMBINED_EDGE_HANDLE_RADIUS = 3.5;
const EDGE_HANDLE_RADIUS = 5;
const EDGE_HANDLE_LINE_WIDTH = 1.5;
/** Screen pixels within which a click lands on an edge handle, or on a join's curve. */
const HANDLE_HIT_RADIUS = 9;
const CONNECTION_HIT_RADIUS = 6;
const BEZIER_HANDLE_RADIUS = 4;
const BEZIER_HANDLE_LINE_WIDTH = 1;

interface DragState {
  startWorld: Point;
  starts: Map<number, [number, number]>;
}

interface RotateState {
  centre: Point;
  lastAngle: number;
}

/** A join being dragged: its first end is pressed, and the release picks the second. */
interface PendingJoin {
  shape: number;
  edge: number;
}

interface HandleDrag {
  connectionId: number;
  end: End;
}

/**
 * The drawing area: draws the net, and turns pointer and wheel input into the Builder's moves, with the
 * same gestures as the Python builder. Move mode: drop, click/Ctrl+click, marquee, drag, right-drag to rotate
 * or pan, scroll to zoom. Join mode: drag from an edge handle to another free edge's handle and release, to
 * join them; click a join to select it, drag its red handles to bend it.
 */
export class BuilderCanvas {
  private ctx: CanvasRenderingContext2D;
  private scale = 1;
  private offsetX = 0;
  private offsetY = 0;
  /** Mouse position in CSS pixels while the palette shape is armed, so its ghost can follow it. */
  private ghost: Point | null = null;
  private marquee: { x0: number; y0: number; x1: number; y1: number; additive: boolean } | null = null;
  private drag: DragState | null = null;
  private rotate: RotateState | null = null;
  private panLast: Point | null = null;
  private pending: PendingJoin | null = null;
  /** The edge handle the pending join would connect to, while the cursor is over one. */
  private hover: PendingJoin | null = null;
  private pendingCursor: Point | null = null;
  private handleDrag: HandleDrag | null = null;
  private centred = false;
  /** Debug mode (the page's D key): shows the owner's anchor glyph. Only the combined page uses it. */
  debug = false;
  /** While true (e.g. a Slow untangle in progress, or the 3D view running), every edit gesture -- drag,
   * rotate, join, marquee-select, dropping an armed shape -- is refused, but panning (right-drag) and
   * zooming (the wheel) still work: those only move the camera, not the net. */
  locked = false;
  /** The piece under the pointer (drawn with a yellow outline), or null. Set by the pointer; the page can set it too. */
  hoverPiece: number | null = null;
  /** Called when the piece under the pointer changes (null when the pointer leaves the pieces). */
  onHoverPiece: ((id: number | null) => void) | null = null;
  /** The edge under the pointer (its join's bezier, its edge circle, or its polygon line), or null. */
  hoverEdge: { shape: number; edge: number } | null = null;
  /** The selected open edge (a joined edge selects its join instead). Set by the page. */
  selectedEdge: { shape: number; edge: number } | null = null;
  /** Called when the edge under the pointer changes. */
  onHoverEdge: ((edge: { shape: number; edge: number } | null) => void) | null = null;
  /** Called when a polygon line is clicked (not a join gesture): the page selects that edge's group. */
  onSelectEdge: ((edge: { shape: number; edge: number }) => void) | null = null;
  /** A piece's fill colour as a CSS colour. Set by the page (its Colour menu); the default is the polygon colour. */
  fillOf: (shape: Shape) => string = (shape) => shapeCssColor(shape.n);
  /** Paints a shape's texture if it has one; returns false to fall back to fillOf. */
  fillTexture: (shape: Shape, verts: [number, number][], ctx: CanvasRenderingContext2D) => boolean = () => false;
  /** Each piece's reachable/role classification for this redraw. Empty outside combined mode. */
  private faces: Map<number, FaceInfo> = new Map();

  constructor(
    private canvas: HTMLCanvasElement,
    private builder: Builder,
    /** Called after every change to the net or its selection, so the page can refresh its menus and title. */
    private onChange: () => void,
    /**
     * Move and Join in one mode, as the Python builder's Edit mode: a press on an edge handle or a join
     * starts a join, anything else moves shapes, and the handles are always shown. Ignores builder.mode.
     */
    private combined = false,
  ) {
    this.ctx = canvas.getContext("2d")!;
    new ResizeObserver(() => this.resize()).observe(canvas.parentElement!);
    canvas.addEventListener("contextmenu", (e) => e.preventDefault());
    canvas.addEventListener("pointerdown", (e) => this.onPointerDown(e));
    canvas.addEventListener("pointermove", (e) => this.onPointerMove(e));
    canvas.addEventListener("pointerup", (e) => this.onPointerUp(e));
    canvas.addEventListener("pointerleave", () => {
      this.ghost = null;
      this.hover = null;
      this.setHoverPiece(null);
      this.redraw();
    });
    canvas.addEventListener("wheel", (e) => this.onWheel(e), { passive: false });
    this.resize();
  }

  /** The zoom level, saved with a net so reopening it keeps the same size. */
  get viewScale(): number {
    return this.scale;
  }

  /** Whether a join is part-way made (its first edge chosen). */
  get isPending(): boolean {
    return this.pending !== null;
  }

  setViewScale(scale: number) {
    this.scale = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, scale));
    this.redraw();
  }

  /** Where the drawing sits on the canvas (the pan), in CSS pixels. Saved with a model so it reopens in the same place. */
  get viewOffset(): [number, number] {
    return [this.offsetX, this.offsetY];
  }

  setViewOffset(x: number, y: number) {
    this.offsetX = x;
    this.offsetY = y;
    this.redraw();
  }

  /** Drops a join that's waiting for its second edge (Escape, or a mode change). */
  cancelPending() {
    this.pending = null;
    this.hover = null;
    this.redraw();
  }

  /** Redraws everything. The page calls this after anything that changes what's shown. */
  redraw() {
    const { ctx, builder } = this;
    const width = this.canvas.clientWidth;
    const height = this.canvas.clientHeight;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    ctx.fillStyle = "#1c1c1c";
    ctx.fillRect(0, 0, width, height);

    this.dropStalePending();

    this.faces = this.combined ? faceInfo(builder.shapes, builder.connections, builder.ownerShapeId()) : new Map();
    // A slow untangle in progress hides whatever it hasn't revealed yet (see Builder.isRevealed) -- a
    // purely 2D drawing concern, so builder.shapes/connections themselves are untouched.
    for (const shape of builder.shapes) {
      if (!builder.isRevealed(shape.id)) continue;
      this.drawShape(shape, builder.selected.has(shape.id));
    }

    const joined = builder.joinedEdges();
    for (const conn of builder.connections) {
      if (!builder.isRevealed(conn.aShape) || !builder.isRevealed(conn.bShape)) continue;
      const touchesSelection = builder.selected.has(conn.aShape) || builder.selected.has(conn.bShape);
      this.drawConnection(conn, conn.id === builder.selectedConnection || touchesSelection);
    }
    this.drawEdgeGroups();

    if (this.pending && this.pendingCursor) {
      const from = builder.shapeById(this.pending.shape);
      if (from) {
        const anchor = this.toScreen(...edgeMidpoints(from)[this.pending.edge]);
        this.strokeLine(anchor, this.pendingCursor, SELECTION_COLOR, CONNECTION_SELECTED_WIDTH);
      }
    }

    if (this.showsJoin()) {
      this.drawEdgeHandles(joined);
      this.drawBezierHandles();
    }

    if (builder.armedN !== null && this.ghost) {
      const [wx, wy] = this.toWorld(this.ghost[0], this.ghost[1]);
      this.drawShape({ id: -1, n: builder.armedN, cx: wx, cy: wy, rotation: 0, flipped: false }, true);
    }
    if (this.marquee) {
      const { x0, y0, x1, y1 } = this.marquee;
      ctx.save();
      ctx.setLineDash([5, 5]);
      ctx.strokeStyle = "white";
      ctx.lineWidth = 1;
      ctx.strokeRect(Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0));
      ctx.restore();
    }
  }

  /** Sizes the canvas to its area. The first time, the origin is centred in it. */
  private resize() {
    const parent = this.canvas.parentElement!;
    const width = parent.clientWidth;
    const height = parent.clientHeight;
    if (!this.centred) {
      this.offsetX = width / 2;
      this.offsetY = height / 2;
      this.centred = true;
    }
    this.canvas.style.width = `${width}px`;
    this.canvas.style.height = `${height}px`;
    this.canvas.width = Math.max(1, Math.round(width * devicePixelRatio));
    this.canvas.height = Math.max(1, Math.round(height * devicePixelRatio));
    this.redraw();
  }

  private toWorld(sx: number, sy: number): Point {
    return [(sx - this.offsetX) / this.scale, (sy - this.offsetY) / this.scale];
  }

  private toScreen(wx: number, wy: number): Point {
    return [wx * this.scale + this.offsetX, wy * this.scale + this.offsetY];
  }

  /** A pending join whose shape was deleted, or whose edge got joined elsewhere (undo), has nothing to finish. */
  private dropStalePending() {
    if (!this.pending) return;
    const shape = this.builder.shapeById(this.pending.shape);
    const edgeJoined = this.builder.joinedEdges().has(`${this.pending.shape}:${this.pending.edge}`);
    if (!shape || edgeJoined) {
      this.pending = null;
      this.hover = null;
    }
  }

  private strokeLine(from: Point, to: Point, color: string, width: number) {
    const { ctx } = this;
    ctx.beginPath();
    ctx.moveTo(from[0], from[1]);
    ctx.lineTo(to[0], to[1]);
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.stroke();
  }

  private drawShape(shape: Shape, selected: boolean) {
    const { ctx } = this;
    const verts = shapeVertices(shape).map(([x, y]) => this.toScreen(x, y));
    const fill = this.fillOf(shape);
    const info = this.faces.get(shape.id);
    const dimmed = info !== undefined && !info.reachable;
    ctx.globalAlpha = dimmed ? UNREACHABLE_OPACITY : 1;

    ctx.beginPath();
    verts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.closePath();
    if (shape.flipped) {
      // A flipped shape reads as its other side: diagonal hatching clipped to the polygon.
      ctx.fillStyle = "#1c1c1c";
      ctx.fill();
      ctx.save();
      ctx.clip();
      ctx.strokeStyle = fill;
      ctx.lineWidth = HATCH_WIDTH;
      const w = this.canvas.clientWidth;
      const h = this.canvas.clientHeight;
      for (let x = -h; x < w; x += HATCH_SPACING) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x + h, h);
        ctx.stroke();
      }
      ctx.restore();
    } else if (!this.fillTexture(shape, verts, ctx)) {
      ctx.fillStyle = fill;
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    // A selected piece keeps its red outline even while hovered.
    if (shape.id === this.hoverPiece && !selected) {
      ctx.strokeStyle = HOVER_COLOR;
      ctx.lineWidth = 3;
      ctx.beginPath();
      verts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      ctx.closePath();
      ctx.stroke();
    }
    if (dimmed) {
      // Unreachable: a dashed outline instead of the solid one, red when selected.
      this.strokeDashedOutline(verts, selected ? SELECTION_COLOR : OUTER_OUTLINE_COLOR);
    } else {
      this.strokeOuterOutline(verts);
      if (selected) {
        ctx.strokeStyle = SELECTION_COLOR;
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }
    if (info?.role) this.drawRoleMark(shape, info.role, info.joins);
  }

  private strokeDashedOutline(verts: Point[], color: string) {
    const { ctx } = this;
    ctx.beginPath();
    verts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.closePath();
    ctx.strokeStyle = color;
    ctx.lineWidth = OUTER_OUTLINE_WIDTH;
    ctx.setLineDash([5, 5]);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  /**
   * Debug mode only: the face category at the piece's centre. The owner is a six-pointed star (filled with two
   * or more joins), a junction a filled triangle, a terminal a hollow one.
   */
  private drawRoleMark(shape: Shape, role: FaceRole, joins: number) {
    if (!this.debug) return;
    // A mark is at most a third of its face's diameter, and shrinks with it when zoomed out.
    const radius = Math.min(MARK_RADIUS, this.faceDiameter(shape.n) / 6);
    if (radius < MIN_DRAWN_RADIUS) return;
    const { ctx } = this;
    const [sx, sy] = this.toScreen(shape.cx, shape.cy);
    ctx.beginPath();
    if (role === "owner") {
      // Filled with two or more joins, unfilled as a terminal.
      // A six-pointed star: an upward and a downward triangle, the same size as the other faces' marks.
      trianglePath(ctx, sx, sy, radius);
      trianglePath(ctx, sx, sy, radius, Math.PI);
      if (joins >= 2) {
        ctx.fillStyle = HANDLE_COLOR;
        ctx.fill();
      } else {
        ctx.strokeStyle = HANDLE_COLOR;
        ctx.lineWidth = EDGE_HANDLE_LINE_WIDTH;
        ctx.stroke();
      }
      return;
    }
    trianglePath(ctx, sx, sy, radius);
    if (role === "junction") {
      ctx.fillStyle = HANDLE_COLOR;
      ctx.fill();
    } else {
      ctx.strokeStyle = HANDLE_COLOR;
      ctx.lineWidth = EDGE_HANDLE_LINE_WIDTH;
      ctx.stroke();
    }
  }

  /**
   * A thin white line just outside the polygon, on every shape. The offset scales the regular polygon out from
   * its centre, so every edge moves out by the same distance.
   */
  private strokeOuterOutline(verts: Point[]) {
    const { ctx } = this;
    const n = verts.length;
    const cx = verts.reduce((sum, [x]) => sum + x, 0) / n;
    const cy = verts.reduce((sum, [, y]) => sum + y, 0) / n;
    const [x0, y0] = verts[0];
    const [x1, y1] = verts[1];
    const apothem = Math.hypot((x0 + x1) / 2 - cx, (y0 + y1) / 2 - cy) || 1;
    // The line's inner edge sits a little inside the fill's edge, so no background shows between them.
    const scale = (apothem + OUTER_OUTLINE_WIDTH / 2 - 0.5) / apothem;
    ctx.beginPath();
    verts.forEach(([x, y], i) => {
      const px = cx + (x - cx) * scale;
      const py = cy + (y - cy) * scale;
      if (i) ctx.lineTo(px, py);
      else ctx.moveTo(px, py);
    });
    ctx.closePath();
    ctx.strokeStyle = OUTER_OUTLINE_COLOR;
    ctx.lineWidth = OUTER_OUTLINE_WIDTH;
    ctx.stroke();
  }

  /** A join's bezier, in screen space. Null if one of its shapes is gone. */
  private connectionCurve(conn: Connection): Point[] | null {
    const geometry = connectionGeometry(conn, (id) => this.builder.shapeById(id));
    if (!geometry) return null;
    const [p0, p1, p2, p3] = geometry.map(([x, y]) => this.toScreen(x, y)) as [Point, Point, Point, Point];
    return sampleCubic(p0, p1, p2, p3);
  }

  private drawConnection(conn: Connection, highlighted: boolean) {
    const curve = this.connectionCurve(conn);
    if (!curve) return;
    const { ctx } = this;
    ctx.beginPath();
    curve.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.strokeStyle = highlighted ? SELECTION_COLOR : CONNECTION_COLOR;
    ctx.lineWidth = highlighted ? CONNECTION_SELECTED_WIDTH : CONNECTION_WIDTH;
    ctx.stroke();
  }

  /**
   * An edge circle's radius: its diameter is at most a fifth of the shape's side length on screen, so the
   * circles shrink as the view is zoomed out.
   */
  private edgeHandleRadius(): number {
    const base = this.combined ? COMBINED_EDGE_HANDLE_RADIUS : EDGE_HANDLE_RADIUS;
    const side = DEFAULT_SHAPE_EDGE_LENGTH * this.scale;
    return Math.min(base, side / 10);
  }

  /** On-screen diameter of an n-sided face: twice its circumradius (the side length fixes that). */
  private faceDiameter(n: number): number {
    return (DEFAULT_SHAPE_EDGE_LENGTH * this.scale) / Math.sin(Math.PI / n);
  }

  /** Join mode shows every edge's handle: a solid white dot if the edge is joined, a ring if it's free, red if it's the current target. */
  private drawEdgeHandles(joined: Set<string>) {
    const { ctx } = this;
    const radius = this.edgeHandleRadius();
    if (radius < MIN_DRAWN_RADIUS) return;
    for (const shape of this.builder.shapes) {
      if (!this.builder.isRevealed(shape.id)) continue;
      edgeMidpoints(shape).forEach((mid, edge) => {
        const [sx, sy] = this.toScreen(...mid);
        const lit =
          (this.pending?.shape === shape.id && this.pending.edge === edge) ||
          (this.hover?.shape === shape.id && this.hover.edge === edge);
        ctx.beginPath();
        ctx.arc(sx, sy, radius, 0, Math.PI * 2);
        if (lit) {
          ctx.fillStyle = SELECTION_COLOR;
          ctx.fill();
        } else if (this.combined || joined.has(`${shape.id}:${edge}`)) {
          ctx.fillStyle = HANDLE_COLOR;
          ctx.fill();
        } else {
          ctx.strokeStyle = HANDLE_COLOR;
          ctx.lineWidth = EDGE_HANDLE_LINE_WIDTH;
          ctx.stroke();
        }
      });
    }
  }

  /** The selected join's two control points, each with a line back to its edge. Only shown in Join mode. */
  private drawBezierHandles() {
    const conn = this.builder.connections.find((c) => c.id === this.builder.selectedConnection);
    if (!conn) return;
    const geometry = connectionGeometry(conn, (id) => this.builder.shapeById(id));
    if (!geometry) return;
    const [aMid, aCtrl, bCtrl, bMid] = geometry.map(([x, y]) => this.toScreen(x, y)) as [Point, Point, Point, Point];
    for (const [mid, ctrl] of [
      [aMid, aCtrl],
      [bMid, bCtrl],
    ] as [Point, Point][]) {
      this.strokeLine(mid, ctrl, SELECTION_COLOR, BEZIER_HANDLE_LINE_WIDTH);
      this.ctx.beginPath();
      this.ctx.arc(ctrl[0], ctrl[1], BEZIER_HANDLE_RADIUS, 0, Math.PI * 2);
      this.ctx.fillStyle = SELECTION_COLOR;
      this.ctx.fill();
    }
  }

  /** The edge handle under a screen point, nearest first, or null. `exclude` is an edge that can't be the target (a join's own start). */
  private handleHit(sx: number, sy: number, exclude: PendingJoin | null): PendingJoin | null {
    const joined = this.builder.joinedEdges();
    let best: PendingJoin | null = null;
    let bestDist = HANDLE_HIT_RADIUS;
    for (const shape of this.builder.shapes) {
      edgeMidpoints(shape).forEach((mid, edge) => {
        if (exclude && exclude.shape === shape.id && exclude.edge === edge) return;
        if (joined.has(`${shape.id}:${edge}`)) return;
        const [mx, my] = this.toScreen(...mid);
        const dist = Math.hypot(sx - mx, sy - my);
        if (dist <= bestDist) {
          best = { shape: shape.id, edge };
          bestDist = dist;
        }
      });
    }
    return best;
  }

  /** The join whose curve passes under a screen point, or null. */
  private connectionHit(sx: number, sy: number): number | null {
    let best: number | null = null;
    let bestDist = CONNECTION_HIT_RADIUS;
    for (const conn of this.builder.connections) {
      const curve = this.connectionCurve(conn);
      if (!curve) continue;
      let dist = Infinity;
      for (let i = 0; i < curve.length - 1; i++) {
        dist = Math.min(dist, distanceToSegment([sx, sy], curve[i], curve[i + 1]));
      }
      if (dist < bestDist) {
        best = conn.id;
        bestDist = dist;
      }
    }
    return best;
  }

  /** Which control point of the selected join is under a screen point: its A or B end, or null. */
  private bezierHandleHit(sx: number, sy: number): End | null {
    const conn = this.builder.connections.find((c) => c.id === this.builder.selectedConnection);
    if (!conn) return null;
    const geometry = connectionGeometry(conn, (id) => this.builder.shapeById(id));
    if (!geometry) return null;
    const aCtrl = this.toScreen(...geometry[1]);
    const bCtrl = this.toScreen(...geometry[2]);
    if (Math.hypot(sx - aCtrl[0], sy - aCtrl[1]) <= HANDLE_HIT_RADIUS) return "a";
    if (Math.hypot(sx - bCtrl[0], sy - bCtrl[1]) <= HANDLE_HIT_RADIUS) return "b";
    return null;
  }

  /** Whether join gestures apply: always in combined mode, otherwise only in Join mode. */
  private showsJoin(): boolean {
    return this.combined || this.builder.mode === "join";
  }

  /** Whether right-drag rotates the selection: in combined mode always, otherwise only in Move mode. */
  private showsMoveRotate(): boolean {
    return this.combined || this.builder.mode === "move";
  }

  /** Combined mode: whether a press at this point belongs to a join rather than a move. */
  private isJoinPress(sx: number, sy: number): boolean {
    return (
      this.pending !== null ||
      this.handleHit(sx, sy, null) !== null ||
      this.bezierHandleHit(sx, sy) !== null ||
      this.connectionHit(sx, sy) !== null
    );
  }

  private onPointerDown(e: PointerEvent) {
    const sx = e.offsetX;
    const sy = e.offsetY;
    this.canvas.setPointerCapture(e.pointerId);
    if (e.button === 0) {
      // Locked: a left press neither edits nor selects -- only panning and zooming stay live.
      if (this.locked) {
        // empty
      } else if (this.combined) {
        const line = this.isJoinPress(sx, sy) ? null : this.polygonEdgeHit(sx, sy);
        if (this.isJoinPress(sx, sy)) this.onJoinPress(sx, sy);
        else if (line) {
          this.onSelectEdge?.(line);
        } else {
          this.builder.selectConnection(null);
          this.onMovePress(e, sx, sy);
        }
      } else if (this.builder.mode === "join") this.onJoinPress(sx, sy);
      else this.onMovePress(e, sx, sy);
    } else if (e.button === 2) {
      // Locked: never rotate the selection, right-drag always just pans.
      const centre = !this.locked && this.showsMoveRotate() ? this.builder.selectionCentre() : null;
      if (centre) {
        const [cx, cy] = this.toScreen(centre[0], centre[1]);
        this.builder.beginGesture();
        this.rotate = { centre, lastAngle: Math.atan2(sy - cy, sx - cx) };
      } else {
        this.panLast = [sx, sy];
      }
    }
    this.redraw();
    this.onChange();
  }

  private onMovePress(e: PointerEvent, sx: number, sy: number) {
    const [wx, wy] = this.toWorld(sx, sy);
    if (this.builder.armedN !== null) {
      this.builder.drop(wx, wy);
      return;
    }
    const hit = this.builder.hitTest(wx, wy);
    if (!hit) {
      this.builder.clickEmpty(e.ctrlKey);
      this.marquee = { x0: sx, y0: sy, x1: sx, y1: sy, additive: e.ctrlKey };
      return;
    }
    this.builder.clickShape(hit, e.ctrlKey);
    // A shape that's (now) part of the selection drags the whole group, so it moves together.
    if (this.builder.selected.has(hit.id)) {
      const starts = new Map<number, [number, number]>();
      for (const s of this.builder.selectedShapes) starts.set(s.id, [s.cx, s.cy]);
      this.builder.beginGesture();
      this.drag = { startWorld: [wx, wy], starts };
    }
  }

  /**
   * Join mode: a press on a free edge handle starts a join, which the drag carries to another free handle and
   * the release completes (see onPointerUp). A press drags a selected join's control point, or selects a join.
   * Shapes can't be picked here, as in the Python builder.
   */
  private onJoinPress(sx: number, sy: number) {
    if (this.builder.selectedConnection !== null) {
      const end = this.bezierHandleHit(sx, sy);
      if (end) {
        this.builder.beginGesture();
        this.handleDrag = { connectionId: this.builder.selectedConnection, end };
        return;
      }
    }
    const start = this.handleHit(sx, sy, null);
    if (start) {
      this.pending = start;
      this.pendingCursor = [sx, sy];
      this.builder.selectConnection(null);
      return;
    }
    this.builder.selectConnection(this.connectionHit(sx, sy));
  }

  /** Sets the hovered edge, and tells the page if it changed. */
  setHoverEdge(edge: { shape: number; edge: number } | null) {
    const same = edge === null ? this.hoverEdge === null : this.hoverEdge !== null && this.hoverEdge.shape === edge.shape && this.hoverEdge.edge === edge.edge;
    if (same) return;
    this.hoverEdge = edge;
    this.onHoverEdge?.(edge);
    this.redraw();
  }

  /** Which edge's polygon line is under a screen point (within a few px), or null. */
  private polygonEdgeHit(sx: number, sy: number): { shape: number; edge: number } | null {
    let best: { shape: number; edge: number } | null = null;
    let bestDist = EDGE_LINE_HIT_RADIUS;
    for (const shape of this.builder.shapes) {
      const verts = shapeVertices(shape).map(([x, y]) => this.toScreen(x, y));
      verts.forEach((a, i) => {
        const b = verts[(i + 1) % verts.length];
        const dist = distanceToSegment([sx, sy], a, b);
        if (dist < bestDist) {
          best = { shape: shape.id, edge: i };
          bestDist = dist;
        }
      });
    }
    return best;
  }

  /** The edge a pointer is over in 2D, in priority order: a join's bezier, an open edge's circle, a polygon line. */
  private edgeUnder(sx: number, sy: number): { shape: number; edge: number } | null {
    const conn = this.connectionHit(sx, sy);
    if (conn !== null) {
      const c = this.builder.connections.find((x) => x.id === conn);
      if (c) return { shape: c.aShape, edge: c.aEdge };
    }
    const circle = this.handleHit(sx, sy, null);
    if (circle) return { shape: circle.shape, edge: circle.edge };
    return this.polygonEdgeHit(sx, sy);
  }

  /** Draws the hovered group in yellow and the selected group in red: each edge's line, plus its join's bezier. */
  private drawEdgeGroups() {
    const selected = this.builder.selectedConnection !== null
      ? (() => {
          const c = this.builder.connections.find((x) => x.id === this.builder.selectedConnection);
          return c ? { shape: c.aShape, edge: c.aEdge } : null;
        })()
      : this.selectedEdge;
    if (this.hoverEdge) this.drawEdgeGroup(this.hoverEdge, HOVER_COLOR);
    if (selected) this.drawEdgeGroup(selected, SELECTION_COLOR);
  }

  private drawEdgeGroup(edge: { shape: number; edge: number }, color: string) {
    const { ctx } = this;
    const group = edgeGroup(this.builder.connections, edge.shape, edge.edge);
    if (group.connection) {
      const curve = this.connectionCurve(group.connection);
      if (curve) {
        ctx.beginPath();
        curve.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
        ctx.strokeStyle = color;
        ctx.lineWidth = CONNECTION_SELECTED_WIDTH;
        ctx.stroke();
      }
    }
    for (const e of group.edges) {
      const shape = this.builder.shapeById(e.shape);
      if (!shape) continue;
      const verts = shapeVertices(shape).map(([x, y]) => this.toScreen(x, y));
      const a = verts[e.edge];
      const b = verts[(e.edge + 1) % verts.length];
      ctx.beginPath();
      ctx.moveTo(a[0], a[1]);
      ctx.lineTo(b[0], b[1]);
      ctx.strokeStyle = color;
      ctx.lineWidth = CONNECTION_SELECTED_WIDTH + 1;
      ctx.stroke();
    }
  }

  /** Sets the hovered piece, and tells the page if it changed. */
  setHoverPiece(id: number | null) {
    if (id === this.hoverPiece) return;
    this.hoverPiece = id;
    this.onHoverPiece?.(id);
    this.redraw();
  }

  private onPointerMove(e: PointerEvent) {
    const sx = e.offsetX;
    const sy = e.offsetY;
    if (this.locked) {
      // Locked: nothing to select or edit, and hit-testing doesn't know about hidden pieces (e.g. a Slow
      // untangle not yet revealed them), so leave whatever's hovered alone rather than lighting up one.
      this.setHoverPiece(null);
      this.setHoverEdge(null);
    } else if (!this.drag && !this.handleDrag && this.builder.armedN === null) {
      const shape = this.builder.hitTest(...this.toWorld(sx, sy));
      this.setHoverPiece(shape ? shape.id : null);
      this.setHoverEdge(this.edgeUnder(sx, sy));
    }
    if (this.builder.armedN !== null) this.ghost = [sx, sy];
    if (this.showsJoin()) {
      if (this.pending) {
        this.pendingCursor = [sx, sy];
        this.hover = this.handleHit(sx, sy, this.pending);
      }
      if (this.handleDrag) {
        this.builder.setHandle(this.handleDrag.connectionId, this.handleDrag.end, this.toWorld(sx, sy));
        this.onChange();
      }
    }
    if (this.drag) {
      const [wx, wy] = this.toWorld(sx, sy);
      this.builder.dragSelection(this.drag.starts, wx - this.drag.startWorld[0], wy - this.drag.startWorld[1]);
      this.onChange();
    } else if (this.marquee) {
      this.marquee.x1 = sx;
      this.marquee.y1 = sy;
    } else if (this.rotate) {
      const [cx, cy] = this.toScreen(this.rotate.centre[0], this.rotate.centre[1]);
      const angle = Math.atan2(sy - cy, sx - cx);
      this.builder.rotateSelection(this.rotate.centre, angle - this.rotate.lastAngle);
      this.rotate.lastAngle = angle;
      this.onChange();
    } else if (this.panLast) {
      this.offsetX += sx - this.panLast[0];
      this.offsetY += sy - this.panLast[1];
      this.panLast = [sx, sy];
    }
    this.redraw();
  }

  private onPointerUp(e: PointerEvent) {
    if (this.drag || this.rotate || this.handleDrag) {
      this.builder.commitGesture();
      this.onChange();
    }
    if (this.pending) {
      // Released on another free edge handle: join the two. Anywhere else, the drag is dropped.
      const target = this.handleHit(e.offsetX, e.offsetY, this.pending);
      if (target) this.builder.join(this.pending.shape, this.pending.edge, target.shape, target.edge);
      this.pending = null;
      this.hover = null;
      this.onChange();
    }
    if (this.marquee) {
      const m = this.marquee;
      if (m.x0 !== m.x1 || m.y0 !== m.y1) {
        const [wx0, wy0] = this.toWorld(Math.min(m.x0, m.x1), Math.min(m.y0, m.y1));
        const [wx1, wy1] = this.toWorld(Math.max(m.x0, m.x1), Math.max(m.y0, m.y1));
        this.builder.marqueeSelect(wx0, wy0, wx1, wy1, m.additive);
      }
      this.onChange();
    }
    this.drag = null;
    this.rotate = null;
    this.panLast = null;
    this.marquee = null;
    this.handleDrag = null;
    this.redraw();
  }

  /** Scroll to zoom, keeping the point under the cursor fixed. */
  private onWheel(e: WheelEvent) {
    e.preventDefault();
    const factor = e.deltaY > 0 ? 1 / ZOOM_STEP : ZOOM_STEP;
    const next = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, this.scale * factor));
    const [wx, wy] = this.toWorld(e.offsetX, e.offsetY);
    this.scale = next;
    this.offsetX = e.offsetX - wx * this.scale;
    this.offsetY = e.offsetY - wy * this.scale;
    this.redraw();
  }
}
