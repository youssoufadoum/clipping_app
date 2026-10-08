/**
 * An illustration of the editor layout built from the real design tokens.
 * It shows interface structure only — no fabricated numbers or results.
 */
export function ProductPreview() {
  return (
    <div className="theme-app relative mx-auto w-full max-w-5xl overflow-hidden rounded-2xl border border-border bg-bg shadow-[0_30px_80px_-30px_rgba(60,40,160,0.45)]" aria-label="Illustration of the Virello editor" role="img">
      <div className="flex items-center gap-1.5 border-b border-border px-4 py-3">
        <span className="size-2.5 rounded-full bg-border-strong" />
        <span className="size-2.5 rounded-full bg-border-strong" />
        <span className="size-2.5 rounded-full bg-border-strong" />
      </div>
      <div className="grid grid-cols-12 gap-3 p-3 sm:p-4">
        <div className="col-span-3 hidden space-y-2 sm:block">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className={`flex gap-2 rounded-lg border p-2 ${i === 1 ? "border-accent bg-accent-soft" : "border-border bg-surface"}`}>
              <div className="h-10 w-7 shrink-0 rounded bg-gradient-to-b from-accent/50 to-accent-2/40" />
              <div className="flex-1 space-y-1.5 pt-1">
                <div className="h-1.5 w-4/5 rounded bg-border-strong" />
                <div className="h-1.5 w-1/2 rounded bg-border" />
              </div>
            </div>
          ))}
        </div>
        <div className="col-span-12 flex flex-col gap-3 sm:col-span-6">
          <div className="relative flex aspect-video items-center justify-center overflow-hidden rounded-xl bg-gradient-to-br from-[#1c1640] via-[#141a33] to-[#0f1a2e]">
            <div className="absolute inset-y-0 left-[38%] w-[25%] border-x-2 border-accent bg-white/5" />
            <div className="size-12 rounded-full border border-white/30 bg-white/10" />
          </div>
          <div className="rounded-xl border border-border bg-surface p-3">
            <div className="relative h-8 rounded-md bg-surface-2">
              <div className="absolute inset-y-0 left-[22%] right-[48%] rounded-md border-2 border-accent bg-accent/20" />
              <div className="absolute inset-y-[-4px] left-[35%] w-0.5 bg-fg" />
            </div>
          </div>
        </div>
        <div className="col-span-3 hidden space-y-2 sm:block">
          {["9:16", "1:1", "16:9"].map((r, i) => (
            <div key={r} className={`rounded-lg border px-3 py-2 text-xs ${i === 0 ? "border-accent text-fg" : "border-border text-muted"}`}>
              {r}
            </div>
          ))}
          <div className="mt-3 h-9 rounded-lg bg-accent" />
        </div>
      </div>
    </div>
  );
}
