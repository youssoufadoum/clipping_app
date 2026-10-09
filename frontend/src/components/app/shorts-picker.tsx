"use client";

import { Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";

export type ShortsChoice = "off" | "30" | "60";

export function shortsPayload(choice: ShortsChoice) {
  return choice === "off" ? undefined : { target_seconds: Number(choice), count: 3, captions: true, auto_render: true };
}

/** "AI shorts: Off / 30 seconds / 1 minute" selector shared by upload and link import. */
export function ShortsPicker({ value, onChange }: { value: ShortsChoice; onChange: (v: ShortsChoice) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm" role="radiogroup" aria-label="AI shorts">
      <span className="inline-flex items-center gap-1.5 font-medium">
        <Sparkles className="size-4 text-accent" aria-hidden /> AI shorts
      </span>
      {(
        [
          ["off", "Off"],
          ["30", "30 seconds"],
          ["60", "1 minute"],
        ] as const
      ).map(([v, label]) => (
        <button
          key={v}
          type="button"
          role="radio"
          aria-checked={value === v}
          onClick={() => onChange(v)}
          className={cn(
            "rounded-full border px-3 py-1 transition-colors",
            value === v ? "border-accent bg-accent-soft text-fg" : "border-border text-muted hover:text-fg",
          )}
        >
          {label}
        </button>
      ))}
      <span className="text-xs text-muted">
        {value === "off" ? "Just import — create clips yourself." : "AI picks the best moments and renders captioned vertical shorts."}
      </span>
    </div>
  );
}
