import type { ReactElement, ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { QueryResponse } from "@/lib/api";
import { TierBadge } from "@/components/TierBadge";
import { Citations } from "@/components/Citations";

// Fenced code (```...```) always nests as <pre><code>; a bare inline span (`x`) never has a
// <pre> ancestor — that structural fact is what distinguishes "block" from "inline", not
// whether Claude happened to tag the fence with a language. Extracting the nested <code>
// element's own children here (rather than branching in the `code` component on a
// `language-xxx` className, which is only present when a language was tagged) means expression
// syntax gets the full block treatment even from an untagged ``` fence.
function extractCodeText(children: ReactNode): ReactNode {
  const child = Array.isArray(children) ? children[0] : children;
  if (child && typeof child === "object" && "props" in (child as ReactElement)) {
    return (child as ReactElement<{ children?: ReactNode }>).props.children;
  }
  return children;
}

export function AnswerMessage({ response }: { response: QueryResponse }) {
  return (
    <div className="flex flex-col gap-3">
      <TierBadge tier={response.tier} />
      <div className="prose-answer text-[15px] leading-7 text-ink">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            // Only reached for genuine inline `code` spans — fenced blocks are fully owned by
            // the `pre` override below, which never delegates back to this.
            code: (props) => {
              const { children, ...rest } = props;
              return (
                <code
                  className="rounded bg-surface-raised px-1.5 py-0.5 font-mono text-[13px] text-grounded"
                  {...rest}
                >
                  {children}
                </code>
              );
            },
            pre: (props) => (
              <pre className="my-3 overflow-x-auto rounded-md bg-surface-raised px-3.5 py-3 font-mono text-[13px] leading-6 text-grounded">
                <code>{extractCodeText(props.children)}</code>
              </pre>
            ),
            p: (props) => <p className="mb-3 last:mb-0" {...props} />,
            ul: (props) => <ul className="mb-3 list-disc pl-5" {...props} />,
            ol: (props) => <ol className="mb-3 list-decimal pl-5" {...props} />,
          }}
        >
          {response.answer}
        </ReactMarkdown>
      </div>
      <Citations citations={response.citations} />
    </div>
  );
}
