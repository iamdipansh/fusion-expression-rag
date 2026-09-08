import type { AnswerTier } from "@/lib/api";

const TIER_COPY: Record<AnswerTier, { label: string; hint: string }> = {
  GROUNDED: {
    label: "Grounded",
    hint: "Directly answered by the manual, with page citations.",
  },
  SYNTHESIZED: {
    label: "Synthesized",
    hint: "Composed from verified manual primitives — not a documented recipe.",
  },
  UNVERIFIED: {
    label: "Unverified",
    hint: "Nothing relevant found in the manual. General knowledge only.",
  },
};

const TIER_COLOR_VAR: Record<AnswerTier, string> = {
  GROUNDED: "var(--signal-grounded)",
  SYNTHESIZED: "var(--signal-synthesized)",
  UNVERIFIED: "var(--signal-unverified)",
};

export function TierBadge({ tier }: { tier: AnswerTier }) {
  const copy = TIER_COPY[tier];
  const color = TIER_COLOR_VAR[tier];

  return (
    <div className="flex items-baseline gap-2.5">
      <span
        className="inline-block h-2 w-2 shrink-0 translate-y-[-1px] rounded-full"
        style={{ background: color }}
        aria-hidden
      />
      <span className="text-sm font-medium" style={{ color }}>
        {copy.label}
      </span>
      <span className="text-sm text-ink-faint">{copy.hint}</span>
    </div>
  );
}
