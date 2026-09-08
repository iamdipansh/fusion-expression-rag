"use client";

import { useCallback, useRef, useState } from "react";
import { HeroCurve } from "@/components/HeroCurve";
import { ApiKeyControl } from "@/components/ApiKeyControl";
import { QuestionInput } from "@/components/QuestionInput";
import { AnswerMessage } from "@/components/AnswerMessage";
import { askQuestion, ApiError, type QueryResponse } from "@/lib/api";

interface Turn {
  id: number;
  question: string;
  status: "loading" | "done" | "error";
  response?: QueryResponse;
  error?: string;
}

const EXAMPLE_QUESTIONS = [
  "make a layer bounce like a rubber ball",
  "add a spring overshoot to a keyframed move",
  "add a subtle wiggle to a Text+ layer's position",
];

export default function Home() {
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const nextId = useRef(0);

  const handleAsk = useCallback(
    async (question: string) => {
      const id = nextId.current++;
      setTurns((prev) => [...prev, { id, question, status: "loading" }]);

      try {
        const response = await askQuestion(question, apiKey);
        setTurns((prev) =>
          prev.map((t) => (t.id === id ? { ...t, status: "done", response } : t)),
        );
      } catch (err) {
        const message =
          err instanceof ApiError ? err.message : "Something went wrong reaching the server.";
        setTurns((prev) => (prev.map((t) => (t.id === id ? { ...t, status: "error", error: message } : t))));
      }
    },
    [apiKey],
  );

  const isAsking = turns.some((t) => t.status === "loading");
  const hasStarted = turns.length > 0;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between px-6 py-4">
        <span className="text-sm font-medium tracking-tight text-ink">
          Fusion Expression RAG
        </span>
        <ApiKeyControl apiKey={apiKey} onChange={setApiKey} />
      </header>

      {!hasStarted ? (
        <main className="flex flex-1 flex-col items-center justify-center px-6 pb-24">
          <div className="flex w-full max-w-2xl flex-col items-center text-center">
            <HeroCurve />
            <h1 className="mt-8 max-w-lg text-4xl leading-tight font-medium tracking-tight text-ink">
              Ground Fusion expressions in the manual, not a guess.
            </h1>
            <p className="mt-4 max-w-md text-[15px] leading-6 text-ink-dim">
              Ask how to animate something in Fusion — springs, bounces, ease curves — and get
              syntax checked against the DaVinci Resolve manual, page by page.
            </p>

            <div className="mt-8 w-full max-w-xl">
              <QuestionInput onSubmit={handleAsk} disabled={isAsking} />
            </div>

            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {EXAMPLE_QUESTIONS.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => handleAsk(q)}
                  disabled={isAsking}
                  className="rounded-full border border-line px-3 py-1.5 text-sm text-ink-dim transition-colors hover:border-ink-faint hover:text-ink disabled:opacity-40"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        </main>
      ) : (
        <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-6 pb-40">
          <div className="flex flex-col gap-10 py-6">
            {turns.map((turn) => (
              <div key={turn.id} className="flex flex-col gap-4">
                <p className="text-[15px] leading-6 text-ink-dim">{turn.question}</p>

                {turn.status === "loading" && (
                  <div className="flex items-center gap-2 text-sm text-ink-faint">
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink-faint" />
                    Retrieving and checking against the manual…
                  </div>
                )}

                {turn.status === "error" && (
                  <div
                    className="rounded-md border px-3.5 py-3 text-sm"
                    style={{
                      borderColor: "var(--signal-unverified-dim)",
                      color: "var(--signal-unverified)",
                    }}
                  >
                    {turn.error}
                  </div>
                )}

                {turn.status === "done" && turn.response && (
                  <AnswerMessage response={turn.response} />
                )}
              </div>
            ))}
          </div>

          <div className="fixed inset-x-0 bottom-0 border-t border-line bg-canvas/95 backdrop-blur">
            <div className="mx-auto w-full max-w-2xl px-6 py-4">
              <QuestionInput
                onSubmit={handleAsk}
                disabled={isAsking}
                placeholder="Ask a follow-up…"
              />
            </div>
          </div>
        </main>
      )}
    </div>
  );
}
