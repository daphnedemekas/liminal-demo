import { useState, useEffect, useMemo } from "react";
import type { Project } from "../services/api";

interface Props {
  projects: Project[];
  activeProjectId: number | null;
  onSelectProject: (id: number) => void;
  onNewProject: () => void;
  onGoHome: () => void;
  userName: string;
  onLogout: () => void;
}

const DOMAIN_LABELS: Record<string, string> = {
  work: "Work & Career",
  learning: "Learning & Growth",
  health: "Health & Wellness",
  creative: "Creative & Projects",
  money: "Money & Finances",
  mind: "Mind & Wellbeing",
};

const STATUS_DISPLAY: Record<string, string> = {
  working: "Working...",
  planning: "Planning...",
  done: "Done",
  failed: "Failed",
  waiting_for_user: "Needs input",
  active: "Active",
};

/** Compute the display status for a project.
 *  Show run status only for transient states (working/planning).
 *  Don't surface "failed" in the sidebar — show "Active" instead. */
function displayStatus(p: Project): string {
  const runStatus = p.latest_run_status;
  if (runStatus === "working" || runStatus === "planning") return runStatus;
  if (runStatus === "done") return "done";
  // For "failed" or null, show project-level status (usually "active")
  return p.status || "active";
}

function useTheme() {
  const [dark, setDark] = useState(() => {
    const stored = localStorage.getItem("theme");
    return stored ? stored === "dark" : true;
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);

  return { dark, toggle: () => setDark((d) => !d) };
}

export function Sidebar({ projects, activeProjectId, onSelectProject, onNewProject, onGoHome, userName, onLogout }: Props) {
  const theme = useTheme();
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const homeProject = projects.find((p) => p.domain === "home");
  const otherProjects = projects.filter((p) => p.domain !== "home");

  // Group projects by domain
  const projectsByDomain = useMemo(() => {
    const groups: Record<string, Project[]> = {};
    const ungrouped: Project[] = [];

    for (const p of otherProjects) {
      if (p.domain && p.domain in DOMAIN_LABELS) {
        if (!groups[p.domain]) groups[p.domain] = [];
        groups[p.domain].push(p);
      } else {
        ungrouped.push(p);
      }
    }

    return { groups, ungrouped };
  }, [otherProjects]);

  const toggleDomain = (domain: string) => {
    setCollapsed((prev) => ({ ...prev, [domain]: !prev[domain] }));
  };

  // Build domain sections from project groupings
  const domainSections = useMemo(() => {
    return Object.entries(projectsByDomain.groups).map(([domain, domainProjects]) => ({
      domain,
      label: DOMAIN_LABELS[domain] || domain,
      projects: domainProjects,
    }));
  }, [projectsByDomain]);

  return (
    <div className="sidebar">
      <div className="sidebar-header" onClick={onGoHome}>
        <span className="sidebar-title">Envisage</span>
      </div>

      {/* Home chat */}
      {homeProject && (
        <div
          className={`sidebar-home ${homeProject.id === activeProjectId ? "active" : ""}`}
          onClick={() => onSelectProject(homeProject.id)}
        >
          Home
        </div>
      )}

      <button className="sidebar-new-btn" onClick={onNewProject}>
        + New Project
      </button>

      <div className="project-list">
        {/* Domain sections */}
        {domainSections.map((section) => (
          <div key={section.domain} className="sidebar-domain-section">
            <div className="sidebar-domain-header">
              <span
                className="sidebar-domain-arrow"
                onClick={() => toggleDomain(section.domain)}
              >
                {collapsed[section.domain] ? "\u25B8" : "\u25BE"}
              </span>
              <span className="sidebar-domain-label">
                {section.label}
              </span>
              <span className="sidebar-domain-count">{section.projects.length}</span>
            </div>
            {!collapsed[section.domain] && section.projects.map((p) => (
              <div
                key={p.id}
                className={`project-item domain-child ${p.id === activeProjectId ? "active" : ""}`}
                onClick={() => onSelectProject(p.id)}
              >
                <div className="project-name">{p.name}</div>
                <div className="project-status">
                  <span className={`status-dot ${displayStatus(p)}`} />
                  {STATUS_DISPLAY[displayStatus(p)] || displayStatus(p)}
                </div>
              </div>
            ))}
          </div>
        ))}

        {/* Ungrouped projects */}
        {projectsByDomain.ungrouped.length > 0 && (
          <>
            {domainSections.length > 0 && (
              <div className="sidebar-domain-header sidebar-other-header">
                <span className="sidebar-domain-label">Other</span>
              </div>
            )}
            {projectsByDomain.ungrouped.map((p) => (
              <div
                key={p.id}
                className={`project-item ${p.id === activeProjectId ? "active" : ""}`}
                onClick={() => onSelectProject(p.id)}
              >
                <div className="project-name">{p.name}</div>
                <div className="project-status">
                  <span className={`status-dot ${displayStatus(p)}`} />
                  {STATUS_DISPLAY[displayStatus(p)] || displayStatus(p)}
                </div>
              </div>
            ))}
          </>
        )}

        {otherProjects.length === 0 && (
          <div style={{ padding: "24px 16px", textAlign: "center", color: "var(--text-muted)", fontSize: "13px" }}>
            No projects yet
          </div>
        )}
      </div>

      <div className="sidebar-footer">
        <div className="sidebar-user">
          <span className="sidebar-user-name">{userName}</span>
          <button className="sidebar-logout" onClick={onLogout}>Log out</button>
        </div>
        <button className="theme-toggle" onClick={theme.toggle}>
          {theme.dark ? "Light mode" : "Dark mode"}
        </button>
      </div>
    </div>
  );
}
