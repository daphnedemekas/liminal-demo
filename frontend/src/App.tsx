import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "./services/api";
import type { User, Project } from "./services/api";
import { WelcomeScreen } from "./components/WelcomeScreen";
import { LoginScreen } from "./components/LoginScreen";
import { DiscoveryView } from "./components/DiscoveryView";
import { Sidebar } from "./components/Sidebar";
import { HomeView } from "./components/HomeView";
import { ChatPanel } from "./components/ChatPanel";
import { ProjectWorkspace } from "./components/ProjectWorkspace";

function App() {
  const [showWelcome, setShowWelcome] = useState(() => {
    // Skip welcome if we have a saved session
    return !localStorage.getItem("envisage_user");
  });
  const [user, setUser] = useState<User | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<number | null>(null);
  const [workspaceRefresh, setWorkspaceRefresh] = useState(0);
  const [chatPanelWidth, setChatPanelWidth] = useState<string>("45%");
  const splitRef = useRef<HTMLDivElement>(null);
  const draggingSplit = useRef(false);
  const discoveryDone = user?.discovery_complete ?? null;

  // Restore user session from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem("envisage_user");
    if (saved) {
      try {
        const parsed = JSON.parse(saved) as User;
        // Verify user still exists on the server
        api.getUser(parsed.id).then((u) => {
          setUser(u);
          setShowWelcome(false);
        }).catch(() => {
          localStorage.removeItem("envisage_user");
        });
      } catch {
        localStorage.removeItem("envisage_user");
      }
    }
  }, []);

  // Save user to localStorage whenever it changes
  useEffect(() => {
    if (user) {
      localStorage.setItem("envisage_user", JSON.stringify(user));
    }
  }, [user]);

  const loadProjects = useCallback(async () => {
    if (!user) return;
    try {
      const list = await api.listProjects(user.id);
      setProjects(list);
    } catch (err) {
      console.error("Failed to load projects:", err);
    }
  }, [user]);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    api.listProjects(user.id).then((list) => {
      if (!cancelled) setProjects(list);
    }).catch((err) => {
      console.error("Failed to load projects:", err);
    });
    return () => { cancelled = true; };
  }, [user]);

  // Periodically refresh projects so background run completions are reflected
  // in the sidebar (e.g. status changes, new artifacts).
  useEffect(() => {
    if (!user) return;
    const interval = setInterval(() => {
      api.listProjects(user.id).then(setProjects).catch(() => {});
    }, 5_000);
    return () => clearInterval(interval);
  }, [user]);

  const handleOnboardingComplete = async () => {
    if (!user) return;
    const updated = await api.getUser(user.id);
    setUser(updated);
    const list = await api.listProjects(updated.id);
    setProjects(list);

    // Auto-select home project
    const home = list.find((p) => p.domain === "home");
    if (home) {
      setActiveProjectId(home.id);
    }
  };

  const handleNewProject = async () => {
    if (!user) return;
    try {
      const project = await api.createProject({
        user_id: user.id,
        name: "New project",
      });
      await loadProjects();
      setActiveProjectId(project.id);
    } catch (err) {
      console.error("Failed to create project:", err);
    }
  };

  const handleSelectProject = (id: number) => {
    setActiveProjectId(id);
  };

  const handleRunComplete = () => {
    setWorkspaceRefresh((k) => k + 1);
    loadProjects();
  };

  const handleNavigateDomain = async (domain: string, context?: string) => {
    if (!user) return;
    try {
      const project = await api.createProject({
        user_id: user.id,
        name: "New project",
        domain,
        description: context,
      });
      await loadProjects();
      setActiveProjectId(project.id);
    } catch (err) {
      console.error("Failed to create project for domain:", err);
    }
  };

  const handleGoHome = () => {
    setActiveProjectId(null);
  };

  const handleLogout = () => {
    localStorage.removeItem("envisage_user");
    setUser(null);
    setProjects([]);
    setActiveProjectId(null);
    setShowWelcome(false);
  };

  const onSplitMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    draggingSplit.current = true;
    const onMouseMove = (ev: MouseEvent) => {
      if (!draggingSplit.current || !splitRef.current) return;
      const rect = splitRef.current.getBoundingClientRect();
      const px = ev.clientX - rect.left;
      const clamped = Math.max(300, Math.min(px, rect.width - 250));
      setChatPanelWidth(`${clamped}px`);
    };
    const onMouseUp = () => {
      draggingSplit.current = false;
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  }, []);

  if (!user) {
    if (showWelcome) {
      return <WelcomeScreen onContinue={() => setShowWelcome(false)} />;
    }
    return <LoginScreen onLogin={setUser} />;
  }

  if (discoveryDone === false) {
    return <DiscoveryView userId={user.id} userName={user.name} onComplete={handleOnboardingComplete} />;
  }

  const activeProject = projects.find((p) => p.id === activeProjectId);
  const isHome = activeProject?.domain === "home";

  // Which view is currently visible
  const showProject = !!activeProject && !isHome;
  const showHome = !showProject;

  return (
    <div className="app-shell">
      <Sidebar
        projects={projects}
        activeProjectId={activeProjectId}
        onSelectProject={handleSelectProject}
        onNewProject={handleNewProject}
        onGoHome={handleGoHome}
        userName={user.name}
        onLogout={handleLogout}
      />
      <main className="main-content">
        {/* Project view — mount when a project is selected, hide/show with CSS */}
        {activeProject && !isHome && (
          <div className="project-split" ref={showProject ? splitRef : undefined} style={{ display: showProject ? undefined : "none" }}>
            <div className="project-split-chat" style={{ width: chatPanelWidth, minWidth: chatPanelWidth }}>
              <ChatPanel
                key={activeProject.id}
                project={activeProject}
                userId={user.id}
                onProjectRenamed={loadProjects}
                onRunComplete={handleRunComplete}
                onNavigateProject={handleSelectProject}
                onMessageReceived={() => { setWorkspaceRefresh((k) => k + 1); loadProjects(); }}
              />
            </div>
            <div className="split-resize-handle" onMouseDown={onSplitMouseDown} />
            <ProjectWorkspace
              projectId={activeProject.id}
              refreshKey={workspaceRefresh}
            />
          </div>
        )}

        {/* Home view — always mounted once user is logged in, hidden when on project */}
        <div style={{ display: showHome ? undefined : "none", height: "100%", overflow: "hidden" }}>
          <HomeView
            projects={projects}
            homeProject={projects.find((p) => p.domain === "home") || null}
            userId={user.id}
            onSelectProject={handleSelectProject}
            onNewProject={handleNewProject}
            onNavigateDomain={handleNavigateDomain}
            onProjectRenamed={loadProjects}
            onRunComplete={handleRunComplete}
            userName={user.name}
          />
        </div>
      </main>
    </div>
  );
}

export default App;
