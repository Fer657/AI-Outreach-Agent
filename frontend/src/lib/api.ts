import type {
  AnalyzeResponse,
  HealthResponse,
  OutreachChannel,
  OutreachMessage,
  ProspectInput,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

export class ApiRequestError extends Error {
  code: string;
  status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = "ApiRequestError";
    this.code = code;
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiRequestError(
      `Could not reach the backend at ${API_BASE}. Is it running?`,
      "network_error",
      0,
    );
  }

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    let code = "http_error";
    try {
      const data = await response.json();
      message = data.message ?? data.detail ?? message;
      code = data.error ?? code;
    } catch {
      // non-JSON error body
    }
    throw new ApiRequestError(String(message), String(code), response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health");
}

export function analyze(prospect: ProspectInput): Promise<AnalyzeResponse> {
  return request<AnalyzeResponse>("/api/analyze", {
    method: "POST",
    body: JSON.stringify(prospect),
  });
}

export function listMessages(prospectId: number): Promise<OutreachMessage[]> {
  return request<OutreachMessage[]>(`/api/prospects/${prospectId}/messages`);
}

export function generateOutreach(
  analysisId: number,
  selection: { problem_title: string; service?: string | null },
): Promise<OutreachMessage[]> {
  return request<OutreachMessage[]>("/api/outreach/generate", {
    method: "POST",
    body: JSON.stringify({ analysis_id: analysisId, ...selection }),
  });
}

export function updateMessage(
  messageId: number,
  update: { content?: string; subject?: string; status?: string },
): Promise<OutreachMessage> {
  return request<OutreachMessage>(`/api/outreach/${messageId}`, {
    method: "PATCH",
    body: JSON.stringify(update),
  });
}

export function approveMessage(messageId: number): Promise<OutreachMessage> {
  return request<OutreachMessage>(`/api/outreach/${messageId}/approve`, {
    method: "POST",
  });
}

export function regenerateMessage(
  messageId: number,
  options?: { channel?: OutreachChannel; instructions?: string },
): Promise<OutreachMessage> {
  return request<OutreachMessage>(`/api/outreach/${messageId}/regenerate`, {
    method: "POST",
    body: JSON.stringify(options ?? {}),
  });
}

export { API_BASE };
