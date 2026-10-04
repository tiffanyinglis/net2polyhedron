import * as THREE from "three";

/**
 * The hexagon texture atlas (hexatlas.png): 16 crocheted hexagons in a 4 x 4 grid, cut from the
 * sample photo. Shared by every viewer; it loads once, and listeners are told when it's ready so the
 * views can redraw.
 */
const ATLAS_URL = new URL("./hexatlas.png", import.meta.url).href;

let texture: THREE.Texture | null = null;
let loaded = false;
const listeners = new Set<() => void>();

export function hexAtlasTexture(): THREE.Texture {
  if (!texture) {
    texture = new THREE.TextureLoader().load(ATLAS_URL, () => {
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
export function hexAtlasImage(): HTMLImageElement | null {
  return loaded && texture ? (texture.image as HTMLImageElement) : null;
}

/** Calls `listener` once the atlas has loaded (or straight away if it already has). Returns an unsubscribe. */
export function onHexAtlasLoaded(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
