"use client";

import { useEffect, useRef, useState } from "react";

const SESSION_STORAGE_KEY = "fusion-rag:anthropic-api-key";

export function ApiKeyControl({
  apiKey,
  onChange,
}: {
  apiKey: string | null;
  onChange: (key: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(apiKey ?? "");
  const containerRef = useRef<HTMLDivElement>(null);

  // sessionStorage is tab-lifetime memory, not disk — clears itself on tab close. Never
  // localStorage. This is a convenience so the key survives a page refresh within the same
  // session, not a persistence layer.
  useEffect(() => {
    try {
      const stored = sessionStorage.getItem(SESSION_STORAGE_KEY);
      if (stored) onChange(stored);
    } catch {
      // Private browsing / storage blocked — key just won't survive a refresh, which is fine.
    }
  }, [onChange]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function save() {
    const trimmed = draft.trim();
    onChange(trimmed || null);
    try {
      if (trimmed) sessionStorage.setItem(SESSION_STORAGE_KEY, trimmed);
      else sessionStorage.removeItem(SESSION_STORAGE_KEY);
    } catch {
      // Ignore — the in-memory value from onChange still works for this page load.
    }
    setOpen(false);
  }

  function clear() {
    setDraft("");
    onChange(null);
    try {
      sessionStorage.removeItem(SESSION_STORAGE_KEY);
    } catch {
      // Nothing to do — no persisted value to worry about either way.
    }
    setOpen(false);
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-md border border-line px-3 py-1.5 text-sm text-ink-dim transition-colors hover:border-ink-faint hover:text-ink"
      >
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{ background: apiKey ? "var(--signal-grounded)" : "var(--ink-faint)" }}
          aria-hidden
        />
        {apiKey ? "Key added" : "Add API key"}
      </button>

      {open && (
        <div className="absolute right-0 z-10 mt-2 w-80 rounded-lg border border-line bg-surface p-4 shadow-lg shadow-black/40">
          <p className="mb-3 text-sm leading-5 text-ink-dim">
            Your key stays in this browser tab. It&apos;s sent with each question and never
            stored on the server.
          </p>
          <input
            type="password"
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && save()}
            placeholder="sk-ant-..."
            className="mb-3 w-full rounded-md border border-line bg-canvas px-3 py-2 font-mono text-sm text-ink placeholder:text-ink-faint focus-visible:outline-2"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={save}
              className="flex-1 rounded-md px-3 py-1.5 text-sm font-medium text-canvas"
              style={{ background: "var(--signal-grounded)" }}
            >
              Save
            </button>
            {apiKey && (
              <button
                type="button"
                onClick={clear}
                className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-dim hover:text-ink"
              >
                Remove
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
