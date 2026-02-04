import { useMemo, useState, useCallback, useRef } from "react";
import type { Project, DiscoveryDomainState } from "../services/api";
import { ChatPanel } from "./ChatPanel";
import { InsightsPanel } from "./InsightsPanel";

const DOMAIN_LABELS: Record<string, string> = {
  work: "Work & Career",
  social: "Social Life",
  studies: "Studies & Learning",
  health: "Health & Wellness",
  hobbies: "Hobbies & Projects",
  money: "Money & Finances",
  mental_health: "Mind & mental health",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "Not started",
  active: "In progress",
  explored: "Explored",
  completed: "Completed",
};

interface Props {
  projects: Project[];
  domains: DiscoveryDomainState[];
  homeProject: Project | null;
  userId: string;
  onSelectProject: (id: number) => void;
  onSelectDomain: (domain: string) => void;
  onNewProject: () => void;
  onProjectRenamed: () => void;
  onRunComplete: () => void;
  userName?: string;
}

export function HomeView({
  projects,
  domains,
  homeProject,
  userId,
  onSelectProject,
  onSelectDomain,
  onNewProject,
  onProjectRenamed,
  onRunComplete,
  userName,
}: Props) {
  const [chatOpen, setChatOpen] = useState(true);
  const [chatWidth, setChatWidth] = useState(420);
  const [insightsRefresh, setInsightsRefresh] = useState(0);
  const dragging = useRef(false);
  const layoutRef = useRef<HTMLDivElement>(null);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
    const onMouseMove = (ev: MouseEvent) => {
      if (!dragging.current || !layoutRef.current) return;
      const rect = layoutRef.current.getBoundingClientRect();
      const newWidth = rect.right - ev.clientX;
      setChatWidth(Math.max(280, Math.min(newWidth, rect.width - 300)));
    };
    const onMouseUp = () => {
      dragging.current = false;
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  }, []);

  const nonHomeProjects = projects.filter((p) => p.domain !== "home");

  const projectsByDomain = useMemo(() => {
    const groups: Record<string, Project[]> = {};
    for (const p of nonHomeProjects) {
      if (p.domain && p.domain in DOMAIN_LABELS) {
        if (!groups[p.domain]) groups[p.domain] = [];
        groups[p.domain].push(p);
      }
    }
    return groups;
  }, [nonHomeProjects]);

  const ungroupedProjects = nonHomeProjects.filter(
    (p) => !p.domain || !(p.domain in DOMAIN_LABELS)
  );

  const totalProjects = nonHomeProjects.length;

  const summaryText =
    domains.length === 0
      ? "Get started by selecting life domains to explore."
      : totalProjects > 0
        ? `${domains.length} domain${domains.length !== 1 ? "s" : ""}, ${totalProjects} project${totalProjects !== 1 ? "s" : ""}`
        : `${domains.length} domain${domains.length !== 1 ? "s" : ""} selected. Explore them to discover projects.`;

  return (
    <div className={`home-layout ${chatOpen ? "chat-open" : ""}`} ref={layoutRef}>
      <div className="home-view">
        <div className="home-header">
          <h1>{userName ? `Welcome, ${userName}` : "Welcome back"}</h1>
          <p className="home-summary">{summaryText}</p>
        </div>

        {domains.length > 0 && (
          <div>
            <div className="section-title">Your domains</div>
            <div className="cards-grid">
              {domains.map((d) => {
                const domainProjects = projectsByDomain[d.domain] || [];
                const label = d.label || DOMAIN_LABELS[d.domain] || d.domain;
                return (
                  <div
                    key={d.domain}
                    className={`domain-card domain-status-${d.status}`}
                    onClick={() => onSelectDomain(d.domain)}
                  >
                    <div className="domain-card-header">
                      <h3>{label}</h3>
                      <span className={`domain-status-badge ${d.status}`}>
                        {STATUS_LABELS[d.status] || d.status}
                      </span>
                    </div>
                    <div className="domain-card-meta">
                      {domainProjects.length > 0
                        ? `${domainProjects.length} project${domainProjects.length !== 1 ? "s" : ""}`
                        : d.status === "pending"
                          ? "Ready to explore"
                          : "No projects yet"}
                    </div>
                    {d.proposed_projects && d.proposed_projects.length > 0 && (
                      <div className="domain-card-proposals">
                        {d.proposed_projects.length} proposed
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <InsightsPanel userId={userId} refreshKey={insightsRefresh} />

        {Object.entries(projectsByDomain).map(([domain, domainProjects]) => (
          <div key={domain} className="domain-section">
            <div className="domain-section-header">
              <span className="section-title" style={{ marginBottom: 0 }}>
                {DOMAIN_LABELS[domain] || domain}
              </span>
              <button
                className="domain-explore-link"
                onClick={() => onSelectDomain(domain)}
              >
                Explore domain
              </button>
            </div>
            <div className="cards-grid">
              {domainProjects.map((p) => (
                <div
                  key={p.id}
                  className="project-card"
                  onClick={() => onSelectProject(p.id)}
                >
                  <h3>{p.name}</h3>
                  <p>{p.description || "No description"}</p>
                  <div className="card-footer">
                    {p.run_count > 0 && (
                      <>
                        <span
                          className={`status-dot ${p.latest_run_status || p.status}`}
                        />
                        <span>{p.run_count} runs</span>
                      </>
                    )}
                    {p.run_count === 0 && (
                      <span className="card-action">Get started</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}

        {ungroupedProjects.length > 0 && (
          <div className="domain-section">
            <div className="section-title">Other projects</div>
            <div className="cards-grid">
              {ungroupedProjects.map((p) => (
                <div
                  key={p.id}
                  className="project-card"
                  onClick={() => onSelectProject(p.id)}
                >
                  <h3>{p.name}</h3>
                  <p>{p.description || "No description"}</p>
                  <div className="card-footer">
                    {p.run_count > 0 && (
                      <>
                        <span
                          className={`status-dot ${p.latest_run_status || p.status}`}
                        />
                        <span>{p.run_count} runs</span>
                      </>
                    )}
                    {p.run_count === 0 && (
                      <span className="card-action">Get started</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="quick-actions">
          <button className="quick-action-btn" onClick={onNewProject}>
            + New Task
          </button>
          {homeProject && !chatOpen && (
            <button
              className="quick-action-btn secondary"
              onClick={() => setChatOpen(true)}
            >
              Open Chat
            </button>
          )}
        </div>
      </div>

      {homeProject && chatOpen && (
        <div
          className="home-chat-resize-handle"
          onMouseDown={onMouseDown}
        />
      )}
      {homeProject && (
        <div
          className={`home-chat-panel ${chatOpen ? "open" : ""}`}
          style={chatOpen ? { width: chatWidth, minWidth: chatWidth } : undefined}
        >
          <button
            className="home-chat-toggle"
            onClick={() => setChatOpen(!chatOpen)}
          >
            {chatOpen ? "Close" : "Chat"}
          </button>
          {chatOpen && (
            <ChatPanel
              project={homeProject}
              userId={userId}
              onProjectRenamed={onProjectRenamed}
              onRunComplete={onRunComplete}
              onNavigateDomain={onSelectDomain}
              onNavigateProject={onSelectProject}
              onMessageReceived={() => setInsightsRefresh((k) => k + 1)}
            />
          )}
        </div>
      )}
    </div>
  );
}
