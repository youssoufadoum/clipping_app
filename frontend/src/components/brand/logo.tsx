import { useId } from "react";

import { cn } from "@/lib/utils";

/**
 * Virello mark: a rounded frame with a play wedge cut into three slices —
 * one long video, divided into shorts.
 */
export function LogoMark({ className }: { className?: string }) {
  // Unique per instance: a duplicated gradient id inside a hidden subtree renders as nothing.
  const id = `vr-g-${useId().replace(/:/g, "")}`;
  return (
    <svg viewBox="0 0 32 32" className={cn("size-7", className)} aria-hidden focusable="false">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#8B6CFF" />
          <stop offset="1" stopColor="#3F7BFF" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="30" height="30" rx="8" fill={`url(#${id})`} />
      <path d="M12 9.5v13l10-6.5z" fill="#fff" />
      <path d="M15.2 8.5v15M18.4 10.5v11" stroke={`url(#${id})`} strokeWidth="1.6" />
    </svg>
  );
}

export function Logo({ className, compact = false }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-semibold tracking-tight text-fg", className)}>
      <LogoMark />
      {!compact && (
        <span className="text-[17px]">
          Virello<span className="font-normal text-muted"> Studio</span>
        </span>
      )}
    </span>
  );
}
