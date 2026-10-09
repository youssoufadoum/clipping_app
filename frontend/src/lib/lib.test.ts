import { describe, expect, it } from "vitest";

import { historyReducer } from "@/components/editor/clip-editor";
import { cropBox, validateRange, type EditorState } from "@/lib/editor";
import { formatBytes, formatDuration, formatTimecode, parseTimecode } from "@/lib/format";
import { safeNext } from "@/lib/redirect";
import { contentTypeFor, validateVideoFile } from "@/lib/upload";

describe("format", () => {
  it("formats durations", () => {
    expect(formatDuration(5)).toBe("0:05");
    expect(formatDuration(65.9)).toBe("1:05");
    expect(formatDuration(3725)).toBe("1:02:05");
    expect(formatDuration(null)).toBe("—");
  });
  it("round-trips timecodes", () => {
    expect(formatTimecode(65.25)).toBe("1:05.3");
    expect(parseTimecode("1:05.3")).toBeCloseTo(65.3);
    expect(parseTimecode("1:02:03")).toBe(3723);
    expect(parseTimecode("42.5")).toBe(42.5);
    expect(parseTimecode("abc")).toBeNull();
    expect(parseTimecode("1:-2")).toBeNull();
    expect(parseTimecode("")).toBeNull();
  });
  it("formats bytes", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(5 * 1024 ** 3)).toBe("5.0 GB");
  });
});

describe("validateRange", () => {
  it("accepts a valid range and rejects invalid ones", () => {
    expect(validateRange(2, 10, 60)).toBeNull();
    expect(validateRange(-1, 10, 60)).toMatch(/beginning/);
    expect(validateRange(5, 61, 60)).toMatch(/within the video/);
    expect(validateRange(5, 5, 60)).toMatch(/after start/);
    expect(validateRange(5, 5.5, 60)).toMatch(/at least/);
    expect(validateRange(0, 700, 800)).toMatch(/at most/);
  });
});

describe("cropBox", () => {
  it("matches the renderer's geometry for landscape to portrait", () => {
    const box = cropBox(1920, 1080, "9:16", "crop", 0.5, 0.5);
    expect(box.axis).toBe("x");
    expect(box.width).toBeCloseTo(0.3164, 3);
    expect(box.left).toBeCloseTo((1 - box.width) / 2, 5);
  });
  it("crops vertically for portrait sources going widescreen", () => {
    const box = cropBox(1080, 1920, "16:9", "crop", 0.5, 0);
    expect(box.axis).toBe("y");
    expect(box.top).toBe(0);
  });
  it("shows the full frame for pad mode and matching ratios", () => {
    expect(cropBox(1920, 1080, "9:16", "pad", 0.5, 0.5).axis).toBeNull();
    expect(cropBox(1920, 1080, "16:9", "crop", 0.5, 0.5).axis).toBeNull();
  });
});

describe("upload validation", () => {
  const file = (name: string, size: number, type = "") => new File([new Uint8Array(size)], name, { type });
  it("rejects unsupported and oversized files", () => {
    expect(validateVideoFile(file("talk.mp4", 10), 100)).toBeNull();
    expect(validateVideoFile(file("talk.MOV", 10), 100)).toBeNull();
    expect(validateVideoFile(file("notes.txt", 10), 100)).toMatch(/Unsupported/);
    expect(validateVideoFile(file("clip.avi", 10), 100)).toMatch(/Unsupported/);
    expect(validateVideoFile(file("big.mp4", 200), 100)).toMatch(/larger/);
    expect(validateVideoFile(file("empty.webm", 0), 100)).toMatch(/empty/);
  });
  it("infers content types", () => {
    expect(contentTypeFor(file("a.mov", 1))).toBe("video/quicktime");
    expect(contentTypeFor(file("a.webm", 1))).toBe("video/webm");
    expect(contentTypeFor(file("a.mp4", 1, "video/mp4"))).toBe("video/mp4");
  });
});

describe("safeNext", () => {
  it("only allows same-origin relative paths", () => {
    expect(safeNext("/projects/1")).toBe("/projects/1");
    expect(safeNext("https://evil.example")).toBe("/dashboard");
    expect(safeNext("//evil.example")).toBe("/dashboard");
    expect(safeNext("/\\evil.example")).toBe("/dashboard");
    expect(safeNext(null)).toBe("/dashboard");
  });
});

describe("sameState", () => {
  it("ignores key order in render settings (JSONB reorders keys)", async () => {
    const { sameState } = await import("@/lib/editor");
    const a = { title: "t", start: 0, end: 5, render: { aspect_ratio: "9:16", fit: "crop", crop_x: 0.2, crop_y: 0.5, pad_color: "black", normalize_audio: false } } as const;
    const reordered = { ...a, render: { fit: "crop", crop_x: 0.2, crop_y: 0.5, pad_color: "black", aspect_ratio: "9:16", normalize_audio: false } } as const;
    expect(sameState(a, reordered)).toBe(true);
    expect(sameState(a, { ...a, render: { ...a.render, crop_x: 0.3 } })).toBe(false);
  });
});

describe("editor history", () => {
  const base: EditorState = {
    title: "Clip",
    start: 0,
    end: 10,
    render: { aspect_ratio: "9:16", fit: "crop", crop_x: 0.5, crop_y: 0.5, pad_color: "black", normalize_audio: false },
  };
  const init = { past: [], present: base, future: [], live: base };

  it("commits, undoes and redoes", () => {
    let h = historyReducer(init, { type: "update", patch: { start: 2 } });
    expect(h.past).toHaveLength(0);
    h = historyReducer(h, { type: "commit" });
    h = historyReducer(h, { type: "update", patch: { end: 8 } });
    h = historyReducer(h, { type: "commit" });
    expect(h.live).toMatchObject({ start: 2, end: 8 });
    h = historyReducer(h, { type: "undo" });
    expect(h.live).toMatchObject({ start: 2, end: 10 });
    h = historyReducer(h, { type: "undo" });
    expect(h.live).toMatchObject({ start: 0, end: 10 });
    h = historyReducer(h, { type: "redo" });
    expect(h.live).toMatchObject({ start: 2, end: 10 });
  });

  it("does not record no-op commits and undo commits pending edits first", () => {
    let h = historyReducer(init, { type: "commit" });
    expect(h.past).toHaveLength(0);
    h = historyReducer(h, { type: "update", patch: { title: "Renamed" } });
    h = historyReducer(h, { type: "undo" });
    expect(h.live.title).toBe("Clip");
    expect(h.future[0].title).toBe("Renamed");
  });
});

describe("parseYouTubeId", async () => {
  const { parseYouTubeId } = await import("@/lib/youtube");
  const id = "dQw4w9WgXcQ";
  it("accepts single-video links", () => {
    for (const url of [
      `https://www.youtube.com/watch?v=${id}`,
      `youtube.com/watch?v=${id}&t=10`,
      `https://youtu.be/${id}?si=x`,
      `https://m.youtube.com/shorts/${id}`,
      `https://www.youtube.com/live/${id}`,
      `  https://youtu.be/${id}  `,
    ]) {
      expect(parseYouTubeId(url)).toBe(id);
    }
  });
  it("rejects other hosts, playlists and malformed ids", () => {
    for (const url of [
      `https://evil.com/watch?v=${id}`,
      `https://youtube.com.evil.com/watch?v=${id}`,
      `https://user:pw@youtube.com/watch?v=${id}`,
      `https://youtube.com:8443/watch?v=${id}`,
      "https://www.youtube.com/playlist?list=PL1",
      "https://www.youtube.com/watch?v=short",
      "hello world",
      "",
    ]) {
      expect(parseYouTubeId(url)).toBeNull();
    }
  });
});
