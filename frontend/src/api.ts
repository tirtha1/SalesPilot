export type Customer = { id: number; name: string; industry: string; location?: string; email?: string; phone?: string; contacts?: Contact[] };
export type Contact = { id: number; customer_id: number; name: string; designation?: string; email?: string; phone?: string };
export type ActionItem = { id: number; customer_id: number; meeting_id?: number; task: string; due_date?: string; status: string; priority: string };
export type Opportunity = { id: number; customer_id: number; name: string; value: string; currency: string; stage: string; probability: number; competitor?: string; expected_close_date?: string };
export type Meeting = { id: number; customer_id: number; contact_id?: number; meeting_date: string; title: string; transcript?: string; summary: string; sentiment?: string; insights?: { type: string; content: string }[]; action_items?: ActionItem[] };
export type Dashboard = { today_follow_ups: ActionItem[]; overdue_actions: ActionItem[]; open_opportunities: Opportunity[]; recent_meetings: Meeting[] };
export type Analysis = { customer_name?: string; contact_name?: string; meeting_date?: string; summary?: string; requirements: string[]; pain_points: string[]; customer_concerns: string[]; competitors: string[]; opportunities: string[]; sentiment?: string; action_items: { task: string; due_date?: string; priority: "LOW" | "MEDIUM" | "HIGH" }[]; follow_up: { required: boolean; date?: string; clarification_needed: boolean }; confidence: { customer: number; contact: number; overall: number } };
export type Brief = { customer_overview: string; relationship_summary: string; recent_discussions: string[]; open_opportunities: string[]; requirements: string[]; pain_points: string[]; competitors: string[]; outstanding_actions: string[]; payment_activity_summary: string; risks: string[]; recommended_talking_points: string[]; recommended_questions: string[]; source: string };

class ApiError extends Error { constructor(message: string) { super(message); this.name = "ApiError"; } }
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { headers: { "Content-Type": "application/json", ...(init?.headers || {}) }, ...init });
  if (!response.ok) { const body = await response.json().catch(() => null); throw new ApiError(body?.error?.message || "Unable to reach SalesPilot."); }
  return response.json() as Promise<T>;
}
export const api = {
  dashboard: () => request<Dashboard>("/api/dashboard"),
  customers: () => request<Customer[]>("/api/customers"),
  customer: (id: number) => request<Customer>(`/api/customers/${id}`),
  history: (id: number) => request<{customer: Customer; meetings: Meeting[]; opportunities: Opportunity[]; action_items: ActionItem[]}>(`/api/customers/${id}/history`),
  brief: (id: number) => request<Brief>(`/api/customers/${id}/brief`),
  actions: () => request<ActionItem[]>("/api/action-items"),
  analyze: (transcript: string) => request<{analysis: Analysis; match: {match_status: string; customer?: {id: number; name: string}; candidates: {id: number; name: string}[]}; source: string}>("/api/meetings/analyze", { method: "POST", body: JSON.stringify({ transcript }) }),
  confirm: (body: unknown) => request<Meeting>("/api/meetings/confirm", { method: "POST", body: JSON.stringify(body) }),
  ask: (question: string) => request<{answer: string; citations: {customer_name?: string; detail: string}[]; source: string}>("/api/ai/ask", { method: "POST", body: JSON.stringify({ question }) }),
  transcribe: async (file: Blob) => {
    const form = new FormData(); form.append("file", file, "salespilot-meeting.webm");
    const response = await fetch("/api/transcription", { method: "POST", body: form });
    if (!response.ok) { const body = await response.json().catch(() => null); throw new ApiError(body?.error?.message || "Transcription failed."); }
    return response.json() as Promise<{transcript: string}>;
  },
};
