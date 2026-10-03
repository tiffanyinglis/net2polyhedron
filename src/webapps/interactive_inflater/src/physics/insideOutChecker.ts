import { type Vec3 } from "./vec3";
import { meshVolume } from "./forces";

/** Detects a relaxOnce trial that settled into a globally inside-out equilibrium relative to
 * where it started -- compares signed enclosed volume sign against a fixed reference (mirrors
 * inside_out_checker.InsideOutChecker). Always False for a reference volume too close to zero
 * (an open net has no reliable sign to compare against). */
export class InsideOutChecker {
  private static readonly MIN_REFERENCE_VOLUME_MAGNITUDE = 1e-6;
  private referenceVolume: number;

  constructor(
    referencePts: Vec3[],
    private facesIdx: number[][],
  ) {
    this.referenceVolume = meshVolume(referencePts, facesIdx);
  }

  isInsideOut(pts: Vec3[]): boolean {
    if (Math.abs(this.referenceVolume) < InsideOutChecker.MIN_REFERENCE_VOLUME_MAGNITUDE) return false;
    const current = meshVolume(pts, this.facesIdx);
    return current < 0 !== this.referenceVolume < 0;
  }
}
