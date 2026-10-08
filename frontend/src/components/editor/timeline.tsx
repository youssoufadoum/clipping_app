"use client";

import { useRef } from "react";

import { formatTimecode } from "@/lib/format";
import { cn } from "@/lib/utils";

type Drag = "start" | "end" | "seek" | null;

/** Trim timeline: drag the handles to set in/out points, click or drag elsewhere to seek. */
export function Timeline({
  duration,
  start,
  end,
  current,
  onChange,
  onCommit,
  onSeek,
}: {
  duration: number;
  start: number;
  end: number;
  current: number;
  onChange: (start: number, end: number) => void;
  onCommit: () => void;
  onSeek: (t: number) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag>(null);
  const pct = (t: number) => `${(Math.min(Math.max(t / Math.max(duration, 0.001), 0), 1) * 100).toFixed(3)}%`;

  const timeAt = (clientX: number) => {
    const rect = ref.current!.getBoundingClientRect();
    const f = Math.min(Math.max((clientX - rect.left) / rect.width, 0), 1);
    return Math.round(f * duration * 10) / 10;
  };

  const move = (clientX: number) => {
    const t = timeAt(clientX);
    if (drag.current === "start") onChange(Math.min(t, end - 1), end);
    else if (drag.current === "end") onChange(start, Math.max(t, start + 1));
    else if (drag.current === "seek") onSeek(t);
  };

  const handle = (which: "start" | "end") => (
    <div
      role="slider"
      tabIndex={0}
      aria-label={which === "start" ? "Clip start" : "Clip end"}
      aria-valuemin={0}
      aria-valuemax={Math.round(duration * 10) / 10}
      aria-valuenow={which === "start" ? start : end}
      aria-valuetext={formatTimecode(which === "start" ? start : end)}
      className="absolute top-0 z-10 flex h-full w-3 -translate-x-1/2 cursor-ew-resize items-center justify-center rounded-sm bg-accent focus-visible:ring-2 focus-visible:ring-fg"
      style={{ left: pct(which === "start" ? start : end) }}
      onPointerDown={(e) => {
        e.stopPropagation();
        drag.current = which;
        (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => drag.current === which && move(e.clientX)}
      onPointerUp={() => {
        drag.current = null;
        onCommit();
      }}
      onKeyDown={(e) => {
        const step = e.shiftKey ? 1 : 0.1;
        const delta = e.key === "ArrowLeft" ? -step : e.key === "ArrowRight" ? step : 0;
        if (!delta) return;
        e.preventDefault();
        const r = (n: number) => Math.round(n * 10) / 10;
        if (which === "start") onChange(r(Math.min(Math.max(0, start + delta), end - 1)), end);
        else onChange(start, r(Math.max(Math.min(duration, end + delta), start + 1)));
        onCommit();
      }}
    >
      <span className="h-4 w-0.5 rounded bg-accent-fg/80" />
    </div>
  );

  return (
    <div className="space-y-1.5 select-none">
      <div
        ref={ref}
        className="relative h-12 cursor-pointer rounded-lg bg-surface-2"
        onPointerDown={(e) => {
          drag.current = "seek";
          (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
          onSeek(timeAt(e.clientX));
        }}
        onPointerMove={(e) => drag.current === "seek" && move(e.clientX)}
        onPointerUp={() => (drag.current = null)}
      >
        <div
          className={cn("absolute inset-y-0 rounded-md border-y-2 border-accent bg-accent/25")}
          style={{ left: pct(start), width: `calc(${pct(end)} - ${pct(start)})` }}
        />
        {handle("start")}
        {handle("end")}
        <div className="pointer-events-none absolute -inset-y-1 z-20 w-0.5 bg-fg" style={{ left: pct(current) }} aria-hidden />
      </div>
      <div className="flex justify-between font-mono text-[11px] text-muted">
        <span>0:00.0</span>
        <span>{formatTimecode(duration)}</span>
      </div>
    </div>
  );
}
