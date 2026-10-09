export function OrDivider({ label = "or upload a file" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-xs text-muted" role="separator">
      <span className="h-px flex-1 bg-border" /> {label} <span className="h-px flex-1 bg-border" />
    </div>
  );
}
