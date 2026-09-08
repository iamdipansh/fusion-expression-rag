import type { Citation } from "@/lib/api";

// Page-number pointers into the official manual, not reproduced text — the manual is Blackmagic's
// copyrighted work (see CLAUDE.md's copyright posture note). Page range and breadcrumb are
// separated by layout (flex gap), not by punctuation like a middle dot or em dash.
export function Citations({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;

  return (
    <div className="mt-4 flex flex-col gap-1.5 border-t border-line pt-4">
      <span className="text-sm text-ink-dim">Sources</span>
      <ul className="flex flex-col gap-1.5">
        {citations.map((c, i) => (
          <li key={i} className="flex items-baseline gap-3 text-sm">
            <span className="shrink-0 font-mono text-xs text-ink-faint">
              p.{c.page_start === c.page_end ? c.page_start : `${c.page_start}–${c.page_end}`}
            </span>
            <span className="text-ink-dim">{c.breadcrumb}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
