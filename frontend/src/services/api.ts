const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const WS_BASE = import.meta.env.VITE_WS_URL || "ws://localhost:8000";

export interface User {
  id: string;
  name: string;
  user_type: string;
  onboarding_complete: boolean;
  default_involvement: string;
  explanation_preference: string;
  model_summary: string;
}

export interface Project {
  id: number;
  name: string;
  description: string;
  status: string;
  involvement_level: string | null;
  budget_limit_cents: number | null;
  budget_spent_cents: number;
  suggested_by_system: boolean;
  created_at: string;
  run_count: number;
  latest_run_status: string | null;
  artifacts?: Artifact[];
}

export interface Run {
  run_id: string;
  project_id: number;
  goal: string;
  status: string;
  result_summary: string;
  cost_cents: number;
  created_at: string;
  events?: RunEvent[];
}

export interface RunEvent {
  id: number;
  event_type: string;
  payload: Record<string, unknown>;
  source_url: string | null;
  source_title: string | null;
  timestamp: string;
}

export interface OnboardingState {
  phase: string;
  gathered_signals: Record<string, unknown>;
  pending_questions: OnboardingQuestion[];
  suggested_projects: OnboardingSuggestion[];
  conversation_history: { role: string; content: string }[];
}

export interface OnboardingQuestion {
  question: string;
  hint: string;
}

export interface OnboardingSuggestion {
  name: string;
  description: string;
}

// Structured artifact content types
export interface ScheduleContent {
  entries: { day: string; time_block: string; activity: string; notes?: string }[];
}

export interface ChecklistContent {
  categories: { name: string; items: { text: string; checked: boolean }[] }[];
}

export interface VideoCollectionContent {
  videos: { title: string; url: string; description: string }[];
}

export interface ResourceListContent {
  resources: { title: string; url: string; description: string; category?: string }[];
}

export type ArtifactContent = ScheduleContent | ChecklistContent | VideoCollectionContent | ResourceListContent | string;

export interface Artifact {
  id: number;
  artifact_type: string;
  title: string;
  content: ArtifactContent;
  sources: { url: string }[];
  created_at: string;
}

export interface SynthesisArtifact {
  type: string;
  title: string;
  content: ArtifactContent;
  sources: string[];
}

export interface SynthesisEvent {
  type: "synthesis";
  summary: string;
  full_output: string;
  artifacts: SynthesisArtifact[];
  suggested_next_steps: string[];
  actions: ChatAction[];
}

export interface ChatAction {
  label: string;
  description: string;
  action_text: string;
}

export interface ChatResponse {
  message: string;
  actions: ChatAction[];
  run_id: string | null;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export const api = {
  login: (name: string) =>
    request<User>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  getUser: (userId: string) => request<User>(`/api/auth/user/${userId}`),

  createProject: (data: { user_id: string; name: string; description?: string }) =>
    request<Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  listProjects: (userId: string) =>
    request<Project[]>(`/api/projects?user_id=${userId}`),

  getProject: (projectId: number) =>
    request<Project>(`/api/projects/${projectId}`),

  updateProject: (projectId: number, data: { name?: string; description?: string }) =>
    request<Project>(`/api/projects/${projectId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  getProjectGreeting: (projectId: number) =>
    request<{ greeting: string }>(`/api/projects/${projectId}/greeting`),

  getMessages: (projectId: number) =>
    request<{ role: string; content: string; actions: ChatAction[]; created_at: string }[]>(
      `/api/projects/${projectId}/messages`,
    ),

  sendChat: (projectId: number, message?: string) =>
    request<ChatResponse>(`/api/projects/${projectId}/chat`, {
      method: "POST",
      body: JSON.stringify({ message: message || null }),
    }),

  createRun: (projectId: number, goal: string) =>
    request<Run>("/api/runs", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, goal }),
    }),

  getRun: (runId: string) => request<Run>(`/api/runs/${runId}`),

  stopRun: (runId: string) =>
    request<{ status: string }>(`/api/runs/${runId}/stop`, { method: "POST" }),

  // Onboarding
  getOnboardingOptions: () =>
    request<{ id: string; label: string; icon: string }[]>("/api/onboarding/options"),

  getOnboardingState: (userId: string) =>
    request<OnboardingState>(`/api/onboarding/state/${userId}`),

  submitQuickContext: (userId: string, selectedIds: string[]) =>
    request<{ phase: string; gathered_signals: Record<string, unknown> }>("/api/onboarding/context", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, selected_ids: selectedIds }),
    }),

  getNextQuestion: (userId: string) =>
    request<{ question: OnboardingQuestion }>("/api/onboarding/next-question", {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    }),

  submitOnboardingAnswer: (userId: string, answer: string) =>
    request<{ gathered_signals: Record<string, unknown>; conversation_history: { role: string; content: string }[]; ready_for_suggestions: boolean }>(
      "/api/onboarding/answer",
      { method: "POST", body: JSON.stringify({ user_id: userId, answer }) },
    ),

  getOnboardingSuggestions: (userId: string) =>
    request<{ suggestions: OnboardingSuggestion[] }>("/api/onboarding/suggestions", {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    }),

  acceptSuggestions: (userId: string, indices: number[]) =>
    request<{ created_projects: { id: number; name: string; description: string }[] }>("/api/onboarding/accept", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, indices }),
    }),

  skipOnboarding: (userId: string) =>
    request<{ status: string }>("/api/onboarding/skip", {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    }),

  getArtifacts: (projectId: number) =>
    request<Artifact[]>(`/api/projects/${projectId}/artifacts`),

  updateArtifact: (projectId: number, artifactId: number, content: ArtifactContent) =>
    request<{ status: string }>(`/api/projects/${projectId}/artifacts/${artifactId}`, {
      method: "PATCH",
      body: JSON.stringify({ content }),
    }),
};

export function createRunWebSocket(runId: string): WebSocket {
  return new WebSocket(`${WS_BASE}/ws/run/${runId}`);
}
