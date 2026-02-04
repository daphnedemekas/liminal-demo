const BASE = import.meta.env.VITE_API_URL || "";
const WS_BASE =
  import.meta.env.VITE_WS_URL ||
  `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`;

export interface User {
  id: string;
  name: string;
  user_type: string;
  onboarding_complete: boolean;
  discovery_complete: boolean;
  default_involvement: string;
  explanation_preference: string;
  model_summary: string;
}

export interface DomainOption {
  id: string;
  label: string;
  icon: string;
}

export interface DiscoveryDomainState {
  domain: string;
  label: string;
  status: string;
  depth: number;
  conversation: { role: string; content: string }[];
  proposed_projects: DiscoveryProposal[];
}

export interface DiscoveryState {
  selected_domains: string[];
  discovery_complete: boolean;
  domains: DiscoveryDomainState[];
  active_domain: string | null;
}

export interface DiscoveryProposal {
  name: string;
  description: string;
  first_goal: string;
  success_metric: string;
  metric_target: string;
}

export interface DiscoveryResponse {
  message: string;
  actions: ChatAction[];
  domain: string | null;
  depth?: number;
  proposed_projects?: DiscoveryProposal[];
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
  domain: string | null;
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

export interface AppContent {
  html: string;
  description?: string;
}

export type ArtifactContent = ScheduleContent | ChecklistContent | VideoCollectionContent | ResourceListContent | AppContent | string;

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
  task_type?: string;
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

  sendChatSSE: async (
    projectId: number,
    message: string | undefined,
    onResearching: (topic: string) => void,
    onMessage: (data: ChatResponse) => void,
    onError: (err: Error) => void,
    onStatus?: (message: string) => void,
    signal?: AbortSignal,
    onResearchActivity?: (tool: string, input: Record<string, unknown>) => void,
  ) => {
    try {
      const res = await fetch(`${BASE}/api/projects/${projectId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: message || null }),
        signal,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || res.statusText);
      }
      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events from buffer
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";

        for (const part of parts) {
          let eventType = "message";
          let data = "";
          for (const line of part.split("\n")) {
            if (line.startsWith("event: ")) eventType = line.slice(7);
            else if (line.startsWith("data: ")) data = line.slice(6);
          }
          if (!data) continue;
          try {
            const parsed = JSON.parse(data);
            if (eventType === "researching") {
              onResearching(parsed.topic);
            } else if (eventType === "status") {
              onStatus?.(parsed.message);
            } else if (eventType === "research_activity") {
              onResearchActivity?.(parsed.tool, parsed.input || {});
            } else if (eventType === "message") {
              onMessage(parsed as ChatResponse);
            }
          } catch {
            // skip malformed events
          }
        }
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      onError(err as Error);
    }
  },

  createRun: (projectId: number, goal: string) =>
    request<Run>("/api/runs", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, goal }),
    }),

  getRun: (runId: string) => request<Run>(`/api/runs/${runId}`),

  getActiveRun: (projectId: number) =>
    request<{ active_run: { run_id: string; status: string; goal: string; created_at: string } | null }>(
      `/api/runs/active/${projectId}`
    ),

  stopRun: (runId: string) =>
    request<{ status: string }>(`/api/runs/${runId}/stop`, { method: "POST" }),

  getArtifacts: (projectId: number) =>
    request<Artifact[]>(`/api/projects/${projectId}/artifacts`),

  updateArtifact: (projectId: number, artifactId: number, content: ArtifactContent) =>
    request<{ status: string }>(`/api/projects/${projectId}/artifacts/${artifactId}`, {
      method: "PATCH",
      body: JSON.stringify({ content }),
    }),

  // Discovery
  getDiscoveryOptions: () =>
    request<DomainOption[]>("/api/discovery/options"),

  selectDomains: (userId: string, domains: string[]) =>
    request<{ domains: { domain: string; label: string; status: string }[] }>("/api/discovery/select-domains", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, domains }),
    }),

  getDiscoveryState: (userId: string) =>
    request<DiscoveryState>(`/api/discovery/state?user_id=${userId}`),

  activateDomain: (userId: string, domain: string) =>
    request<DiscoveryResponse>("/api/discovery/activate-domain", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, domain }),
    }),

  sendDiscoveryResponse: (userId: string, message: string, domain?: string) =>
    request<DiscoveryResponse>("/api/discovery/respond", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, message, domain }),
    }),

  sendDiscoveryResponseSSE: async (
    userId: string,
    message: string,
    domain: string | undefined,
    onStatus: (message: string) => void,
    onMessage: (data: DiscoveryResponse) => void,
    onError: (err: Error) => void,
  ) => {
    try {
      const res = await fetch(`${BASE}/api/discovery/respond`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, message, domain }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || res.statusText);
      }
      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";

        for (const part of parts) {
          let eventType = "message";
          let data = "";
          for (const line of part.split("\n")) {
            if (line.startsWith("event: ")) eventType = line.slice(7);
            else if (line.startsWith("data: ")) data = line.slice(6);
          }
          if (!data) continue;
          try {
            const parsed = JSON.parse(data);
            if (eventType === "status") {
              onStatus(parsed.message);
            } else if (eventType === "message") {
              onMessage(parsed as DiscoveryResponse);
            } else if (eventType === "error") {
              onError(new Error(parsed.detail || "Unknown error"));
            }
          } catch {
            // skip malformed events
          }
        }
      }
    } catch (err) {
      onError(err as Error);
    }
  },

  acceptDiscoveryProjects: (userId: string, projectIndices: number[], domain: string) =>
    request<{ created_projects: { id: number; name: string; description: string }[]; next_domain: string | null; opening: DiscoveryResponse | null; all_complete: boolean }>(
      "/api/discovery/accept-projects",
      { method: "POST", body: JSON.stringify({ user_id: userId, project_indices: projectIndices, domain }) },
    ),

  skipDiscoveryDomain: (userId: string) =>
    request<{ next_domain: string | null; opening: DiscoveryResponse | null; all_complete: boolean }>(
      "/api/discovery/skip-domain",
      { method: "POST", body: JSON.stringify({ user_id: userId }) },
    ),

  runDiscoveryAgent: (userId: string, agentTask: string) =>
    request<DiscoveryResponse>("/api/discovery/run-agent", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, agent_task: agentTask }),
    }),

  completeDiscovery: (userId: string) =>
    request<{ status: string; model_summary: string }>("/api/discovery/complete", {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    }),

  // Context attachments
  uploadText: (data: { user_id: string; project_id?: number; discovery_domain_id?: number; title?: string; text: string }) =>
    request<ContextAttachment>("/api/context/upload-text", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  uploadUrl: (data: { user_id: string; project_id?: number; discovery_domain_id?: number; url: string }) =>
    request<ContextAttachment>("/api/context/upload-url", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  uploadPdf: async (data: { user_id: string; project_id?: number; discovery_domain_id?: number; file: File }): Promise<ContextAttachment> => {
    const form = new FormData();
    form.append("user_id", data.user_id);
    if (data.project_id != null) form.append("project_id", String(data.project_id));
    if (data.discovery_domain_id != null) form.append("discovery_domain_id", String(data.discovery_domain_id));
    form.append("file", data.file);
    const res = await fetch(`${BASE}/api/context/upload-pdf`, { method: "POST", body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    return res.json();
  },

  listContext: (userId: string, projectId?: number, discoveryDomainId?: number) => {
    const params = new URLSearchParams({ user_id: userId });
    if (projectId != null) params.set("project_id", String(projectId));
    if (discoveryDomainId != null) params.set("discovery_domain_id", String(discoveryDomainId));
    return request<ContextAttachment[]>(`/api/context/?${params}`);
  },

  deleteContext: (attachmentId: number) =>
    request<{ status: string }>(`/api/context/${attachmentId}`, { method: "DELETE" }),

  // Insights
  getInsights: (userId: string) =>
    request<InsightsData>(`/api/insights?user_id=${userId}`),
};

export interface InsightItem {
  id: number;
  content: string;
  category?: string;
  confidence: string;
  source_layer: string;
  created_at: string;
}

export interface InsightsData {
  total_count: number;
  categories: Record<string, InsightItem[]>;
  recent: InsightItem[];
  timeline: { week: string; count: number }[];
}

export interface ContextAttachment {
  id: number;
  source_type: string;
  source_ref: string | null;
  title: string | null;
  created_at: string;
}

export function createRunWebSocket(runId: string): WebSocket {
  return new WebSocket(`${WS_BASE}/ws/run/${runId}`);
}
