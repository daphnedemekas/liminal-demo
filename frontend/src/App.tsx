import { useState, useEffect, useCallback } from "react";
import { api } from "./services/api";
import type { User, Project } from "./services/api";
import { LoginScreen } from "./components/LoginScreen";
import { OnboardingView } from "./components/OnboardingView";
import { Sidebar } from "./components/Sidebar";
import { HomeView } from "./components/HomeView";
import { ChatPanel } from "./components/ChatPanel";

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<number | null>(null);
  const onboardingDone = user?.onboarding_complete ?? null;

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

  const handleOnboardingComplete = async () => {
    if (!user) return;
    const updated = await api.getUser(user.id);
    setUser(updated);
    await loadProjects();
  };

  const handleNewProject = async () => {
    if (!user) return;
    try {
      const project = await api.createProject({
        user_id: user.id,
        name: "New task",
      });
      await loadProjects();
      setActiveProjectId(project.id);
    } catch (err) {
      console.error("Failed to create project:", err);
    }
  };

  if (!user) {
    return <LoginScreen onLogin={setUser} />;
  }

  if (onboardingDone === false) {
    return <OnboardingView userId={user.id} userName={user.name} onComplete={handleOnboardingComplete} />;
  }

  const activeProject = projects.find((p) => p.id === activeProjectId);

  return (
    <div className="app-shell">
      <Sidebar
        projects={projects}
        activeProjectId={activeProjectId}
        onSelectProject={setActiveProjectId}
        onNewProject={handleNewProject}
        onGoHome={() => setActiveProjectId(null)}
      />
      <main className="main-content">
        {activeProject ? (
          <ChatPanel
            project={activeProject}
            onProjectRenamed={loadProjects}
          />
        ) : (
          <HomeView
            projects={projects}
            onSelectProject={setActiveProjectId}
            onNewProject={handleNewProject}
            userName={user.name}
          />
        )}
      </main>
    </div>
  );
}

export default App;
