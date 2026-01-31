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
  const [onboardingDone, setOnboardingDone] = useState<boolean | null>(null);

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
    setOnboardingDone(user.onboarding_complete);
    loadProjects();
  }, [user, loadProjects]);

  const handleOnboardingComplete = async () => {
    if (!user) return;
    // Refresh user and projects after onboarding
    const updated = await api.getUser(user.id);
    setUser(updated);
    setOnboardingDone(true);
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

  // Show onboarding for new users (null = still loading check)
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
