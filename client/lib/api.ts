// Mirrors server/app/schemas.py and server/config.py's ContentType/AnswerTier/Sufficiency
// literals. Keep in sync by hand — the server is the source of truth.

export type AnswerTier = "GROUNDED" | "SYNTHESIZED" | "UNVERIFIED";
export type Sufficiency = "sufficient" | "partial" | "insufficient";
export type ContentType =
  | "prose"
  | "table"
  | "parameter_reference"
  | "code_example"
  | "ui_description";

export interface Citation {
  breadcrumb: string;
  page_start: number;
  page_end: number;
  content_type: ContentType;
}

export interface QueryResponse {
  tier: AnswerTier;
  sufficiency: Sufficiency;
  answer: string;
  citations: Citation[];
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

// The API key never leaves this function except as this request's body — see
// components/ApiKeyControl.tsx for where it's held (session-only, never persisted).
export async function askQuestion(
  question: string,
  anthropicApiKey: string | null,
): Promise<QueryResponse> {
  const response = await fetch(`${API_BASE_URL}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      anthropic_api_key: anthropicApiKey || null,
    }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail ?? `Request failed with status ${response.status}`;
    throw new ApiError(detail, response.status);
  }

  return response.json();
}
