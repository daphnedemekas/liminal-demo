import type { Project } from "../services/api";

interface Props {
  projects: Project[];
  onSelectProject: (id: number) => void;
  onNewProject: () => void;
  userName?: string;
}

export function HomeView({ projects, onSelectProject, onNewProject, userName }: Props) {
  const suggestedProjects = projects.filter((p) => p.suggested_by_system && p.run_count === 0);
  const activeProjects = projects.filter((p) => p.run_count > 0 && p.status === "active");

  return (
    <div className="home-view">
      <div className="home-header">
        <h1>{userName ? `Welcome, ${userName}` : "Welcome back"}</h1>
        <p>What do you need help with today?</p>
      </div>

      {suggestedProjects.length > 0 && (
        <div>
          <div className="section-title">Suggested for you</div>
          <div className="cards-grid">
            {suggestedProjects.map((p) => (
              <div key={p.id} className="project-card suggested" onClick={() => onSelectProject(p.id)}>
                <h3>{p.name}</h3>
                <p>{p.description || "Click to get started"}</p>
                <div className="card-footer">
                  <span className="card-action">Start this project &rarr;</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeProjects.length > 0 && (
        <div>
          <div className="section-title">Active Projects</div>
          <div className="cards-grid">
            {activeProjects.map((p) => (
              <div key={p.id} className="project-card" onClick={() => onSelectProject(p.id)}>
                <h3>{p.name}</h3>
                <p>{p.description || "No description"}</p>
                <div className="card-footer">
                  <span className={`status-dot ${p.latest_run_status || p.status}`} />
                  <span>{p.run_count} runs</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="section-title">Or try something new</div>
        <div className="suggestion-chips">
          <button onClick={onNewProject} className="suggestion-chip">
            Research a topic
          </button>
          <button onClick={onNewProject} className="suggestion-chip">
            Compare options
          </button>
          <button onClick={onNewProject} className="suggestion-chip">
            Plan a project
          </button>
        </div>
      </div>
    </div>
  );
}
