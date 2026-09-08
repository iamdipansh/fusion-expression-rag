"use client";

import { useRef } from "react";

export function QuestionInput({
  onSubmit,
  disabled,
  placeholder = "Ask about a Fusion expression, node, or animation…",
}: {
  onSubmit: (question: string) => void;
  disabled: boolean;
  placeholder?: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  function submit() {
    const value = ref.current?.value.trim();
    if (!value || disabled) return;
    onSubmit(value);
    if (ref.current) ref.current.value = "";
  }

  return (
    <div className="flex items-end gap-2 rounded-lg border border-line bg-surface px-3 py-2.5 focus-within:border-ink-faint">
      <textarea
        ref={ref}
        rows={1}
        placeholder={placeholder}
        disabled={disabled}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        onInput={(e) => {
          const el = e.currentTarget;
          el.style.height = "auto";
          el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
        }}
        className="max-h-40 flex-1 resize-none bg-transparent text-[15px] leading-6 text-ink placeholder:text-ink-faint focus:outline-none disabled:opacity-50"
      />
      <button
        type="button"
        onClick={submit}
        disabled={disabled}
        aria-label="Ask"
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-canvas transition-opacity disabled:opacity-40"
        style={{ background: "var(--signal-grounded)" }}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
          <path
            d="M8 13V3M8 3L3.5 7.5M8 3L12.5 7.5"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
    </div>
  );
}
