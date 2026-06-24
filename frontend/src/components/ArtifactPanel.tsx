import type { Artifact } from "../lib/api";

function prettify(slug: string): string {
  return slug.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function ArtifactPanel({
  artifacts,
  activeThread,
  bust,
  width,
  onSelect,
  onResizeStart,
  onClose,
  resizing,
}: {
  artifacts: Artifact[];
  activeThread: string | null;
  bust: number;
  width: number; // percentage of the window
  onSelect: (thread: string) => void;
  onResizeStart: (e: React.PointerEvent) => void;
  onClose: () => void;
  resizing: boolean;
}) {
  const active = artifacts.find((a) => a.thread === activeThread) ?? artifacts[0];
  if (!active) return null;

  return (
    <aside
      className="animate-rise relative flex flex-col border-l border-line bg-paper-sunken/60"
      style={{ width: `${width}%`, minWidth: 360 }}
    >
      {/* Drag handle */}
      <div
        onPointerDown={onResizeStart}
        title="Drag to resize"
        className="group absolute top-0 bottom-0 -left-1.5 z-10 flex w-3 cursor-col-resize items-center justify-center"
      >
        <div
          className={`h-16 w-1 rounded-full transition ${
            resizing ? "bg-leaf" : "bg-line group-hover:bg-sage"
          }`}
        />
      </div>
      {/* Block iframe from eating pointer events mid-drag */}
      {resizing && <div className="absolute inset-0 z-20" />}
      {/* Tab rail */}
      <div className="flex items-center gap-2 overflow-x-auto px-4 pt-4 pb-3">
        <span className="font-mono text-[10px] tracking-[0.2em] text-muted uppercase">
          Artifacts
        </span>
        <span className="h-px flex-shrink-0 grow bg-line" />
        {artifacts.map((a) => {
          const isActive = a.thread === active.thread;
          return (
            <button
              key={a.thread}
              onClick={() => onSelect(a.thread)}
              className={`flex flex-shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 font-mono text-[11px] transition ${
                isActive
                  ? "border-ink bg-ink text-paper shadow-card"
                  : "border-line bg-paper-raised text-muted hover:border-sage hover:text-ink"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  isActive ? "bg-leaf-bright" : "border border-current"
                }`}
              />
              {prettify(a.thread)}
            </button>
          );
        })}
      </div>

      {/* Framed viewport */}
      <div className="min-h-0 flex-1 px-4 pb-4">
        <div className="flex h-full flex-col overflow-hidden rounded-xl border border-line bg-paper-raised shadow-card">
          <div className="flex items-center justify-between border-b border-line px-3.5 py-2">
            <span className="font-mono text-[11px] text-muted">
              {prettify(active.thread)}
            </span>
            <div className="flex items-center gap-3">
              <a
                href={active.url}
                target="_blank"
                rel="noreferrer"
                className="font-mono text-[11px] font-semibold text-leaf-deep hover:underline"
              >
                Open ↗
              </a>
              <button
                onClick={onClose}
                title="Close panel"
                aria-label="Close artifact panel"
                className="flex h-5 w-5 items-center justify-center rounded-md text-muted transition hover:bg-ink/5 hover:text-ink"
              >
                ✕
              </button>
            </div>
          </div>
          {/* sandbox: scripts may run, but no same-origin access to the app */}
          <iframe
            key={`${active.thread}-${bust}`}
            src={`${active.url}?t=${bust}`}
            sandbox="allow-scripts"
            title={prettify(active.thread)}
            className="w-full flex-1 bg-paper"
          />
        </div>
      </div>
    </aside>
  );
}
