import type { AspectRatio, FitMode, RenderSettings } from "@/lib/types";

export const MIN_CLIP_SECONDS = 1;
export const MAX_CLIP_SECONDS = 600;

export interface EditorState {
  title: string;
  start: number;
  end: number;
  render: RenderSettings;
}

const RATIOS: Record<Exclude<AspectRatio, "original">, number> = { "9:16": 9 / 16, "1:1": 1, "16:9": 16 / 9 };

export function round1(n: number): number {
  return Math.round(n * 10) / 10;
}

/** Validation mirrors the API so most mistakes are caught before a round trip. */
export function validateRange(start: number, end: number, duration: number): string | null {
  if (!Number.isFinite(start) || !Number.isFinite(end)) return "Enter valid start and end times.";
  if (start < 0) return "Start can't be before the beginning of the video.";
  if (end > duration + 0.001) return `End must be within the video (${duration.toFixed(1)}s).`;
  if (end <= start) return "End must be after start.";
  if (end - start < MIN_CLIP_SECONDS) return `Clips must be at least ${MIN_CLIP_SECONDS} second long.`;
  if (end - start > MAX_CLIP_SECONDS) return `Clips can be at most ${MAX_CLIP_SECONDS / 60} minutes long.`;
  return null;
}

export interface CropBox {
  left: number;
  top: number;
  width: number;
  height: number;
  axis: "x" | "y" | null;
}

/**
 * The crop window as fractions of the source frame — the same geometry the
 * renderer uses (crop to target aspect, positioned by crop_x/crop_y).
 */
export function cropBox(sourceW: number, sourceH: number, ratio: AspectRatio, fit: FitMode, cropX: number, cropY: number): CropBox {
  if (ratio === "original" || fit === "pad" || !sourceW || !sourceH) {
    return { left: 0, top: 0, width: 1, height: 1, axis: null };
  }
  const target = RATIOS[ratio];
  const source = sourceW / sourceH;
  if (Math.abs(source - target) < 0.005) return { left: 0, top: 0, width: 1, height: 1, axis: null };
  if (source > target) {
    const width = target / source;
    return { left: (1 - width) * cropX, top: 0, width, height: 1, axis: "x" };
  }
  const height = source / target;
  return { left: 0, top: (1 - height) * cropY, width: 1, height, axis: "y" };
}

/** Key-order independent: render settings round-trip through JSONB, which reorders keys. */
export function sameRender(a: RenderSettings, b: RenderSettings): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)] as (keyof RenderSettings)[]);
  for (const k of keys) if (a[k] !== b[k]) return false;
  return true;
}

export function sameState(a: EditorState, b: EditorState): boolean {
  return a.title === b.title && a.start === b.start && a.end === b.end && sameRender(a.render, b.render);
}
