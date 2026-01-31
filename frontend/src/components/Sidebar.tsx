import type { Project } from "../services/api";

interface Props {
  projects: Project[];
  activeProjectId: number | null;
  onSelectProject: (id: number) => void;
  onNewProject: () => void;
  onGoHome: () => void;
}

export function Sidebar({ projects, activeProjectId, onSelectProject, onNewProject, onGoHome }: Props) {
  return (
    <div className="sidebar">
      <div className="sidebar-header" onClick={onGoHome}>
        <span className="sidebar-title">Liminal</span>
      </div>

      <button className="sidebar-new-btn" onClick={onNewProject}>
        + New Task
      </button>

      <div className="project-list">
        {projects.length === 0 && (
          <div style={{ padding: "24px 16px", textAlign: "center", color: "#94a3b8", fontSize: "13px" }}>
            No projects yet
          </div>
        )}
        {projects.map((p) => (
          <div
            key={p.id}
            className={`project-item ${p.id === activeProjectId ? "active" : ""}`}
            onClick={() => onSelectProject(p.id)}
          >
            <div className="project-name">{p.name}</div>
            <div className="project-status">
              <span className={`status-dot ${p.latest_run_status || p.status}`} />
              {p.latest_run_status || p.status}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
