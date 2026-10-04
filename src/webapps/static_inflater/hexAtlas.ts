import * as THREE from "three";

/**
 * The hexagon texture atlas (hexatlas.png): 16 crocheted hexagons in a 4 x 4 grid, cut from the
 * sample photo. Shared by every viewer; it loads once, and listeners are told when it's ready so the
 * views can redraw.
 */
const ATLAS_URL = new URL("./hexatlas.png", import.meta.url).href;

const ATLAS_GRID = 4;
let texture: THREE.Texture | null = null;
let loaded = false;
/** The atlas after darkening (see darkenBlackCells), the picture both the 3D texture and the 2D canvas draw from. */
let processed: HTMLCanvasElement | null = null;
const listeners = new Set<() => void>();

/** The black rim is the band between a hexagon's outer edge (radius 1/2 of the cell) and this inset hexagon. */
const RIM_INNER = 0.925;
/** A rim pixel brighter than this multiple of its cell's median rim brightness is pulled down to that cap. */
const RIM_CAP = 1.25;

/** True if a point (relative to the cell centre, cell units) lies inside a regular hexagon of circumradius `r`, corners at 0, 60, ... degrees. */
function insideHex(px: number, py: number, r: number): boolean {
  for (let k = 0; k < 6; k++) {
    const a = ((30 + 60 * k) * Math.PI) / 180;
    if (px * Math.cos(a) + py * Math.sin(a) > r * Math.cos(Math.PI / 6)) return false;
  }
  return true;
}

/**
 * Caps the brightness of the black rim: a mask of each cell's rim (inside the hexagon, outside its inset copy) and
 * any rim pixel brighter than RIM_CAP times the cell's median rim brightness is pulled down to that cap. Nothing
 * outside the rim is touched.
 */
function darkenRim(image: HTMLImageElement): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = image.width;
  canvas.height = image.height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(image, 0, 0);
  const W = canvas.width;
  const H = canvas.height;
  const img = ctx.getImageData(0, 0, W, H);
  const d = img.data;
  const cellW = W / ATLAS_GRID;
  const cellH = H / ATLAS_GRID;
  for (let cell = 0; cell < ATLAS_GRID * ATLAS_GRID; cell++) {
    const x0 = Math.floor((cell % ATLAS_GRID) * cellW);
    const y0 = Math.floor(Math.floor(cell / ATLAS_GRID) * cellH);
    const x1 = Math.floor(x0 + cellW);
    const y1 = Math.floor(y0 + cellH);
    const rim: { p: number; lum: number }[] = [];
    for (let y = y0; y < y1; y++) {
      for (let x = x0; x < x1; x++) {
        const px = (x + 0.5 - x0) / cellW - 0.5;
        const py = (y + 0.5 - y0) / cellH - 0.5;
        if (!insideHex(px, py, 0.5) || insideHex(px, py, 0.5 * RIM_INNER)) continue;
        const p = y * W + x;
        rim.push({ p, lum: 0.299 * d[p * 4] + 0.587 * d[p * 4 + 1] + 0.114 * d[p * 4 + 2] });
      }
    }
    if (rim.length === 0) continue;
    const sorted = rim.map((r) => r.lum).sort((a, b) => a - b);
    const cap = sorted[Math.floor(sorted.length / 2)] * RIM_CAP;
    for (const { p, lum } of rim) {
      if (lum <= cap) continue;
      const k = cap / lum;
      d[p * 4] *= k;
      d[p * 4 + 1] *= k;
      d[p * 4 + 2] *= k;
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas;
}

export function hexAtlasTexture(): THREE.Texture {
  if (!texture) {
    texture = new THREE.TextureLoader().load(ATLAS_URL, (loadedTexture) => {
      processed = darkenRim(loadedTexture.image as HTMLImageElement);
      texture!.image = processed;
      texture!.needsUpdate = true;
      loaded = true;
      listeners.forEach((listener) => listener());
    });
    texture.colorSpace = THREE.SRGBColorSpace;
  }
  return texture;
}

export function hexAtlasReady(): boolean {
  return loaded;
}

/** Resolves once the atlas has loaded (starts loading it if needed). */
export function hexAtlasLoaded(): Promise<void> {
  hexAtlasTexture();
  if (loaded) return Promise.resolve();
  return new Promise((resolve) => {
    const off = onHexAtlasLoaded(() => {
      off();
      resolve();
    });
  });
}

/** The atlas's pixels, for drawing with canvas 2D; null until it has loaded. */
export function hexAtlasImage(): HTMLCanvasElement | null {
  return loaded ? processed : null;
}

/** Calls `listener` once the atlas has loaded (or straight away if it already has). Returns an unsubscribe. */
export function onHexAtlasLoaded(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
