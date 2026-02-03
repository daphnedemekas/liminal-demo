import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "./services/api";
import type { User, Project, DiscoveryDomainState, DiscoveryProposal } from "./services/api";
import { WelcomeScreen } from "./components/WelcomeScreen";
import { LoginScreen } from "./components/LoginScreen";
import { DiscoveryView } from "./components/DiscoveryView";
import { Sidebar } from "./components/Sidebar";
import { HomeView } from "./components/HomeView";
import { ChatPanel } from "./components/ChatPanel";
import { DomainChat } from "./components/DomainChat";
import { ProjectWorkspace } from "./components/ProjectWorkspace";
import { ProposedProjectsPanel } from "./components/ProposedProjectsPanel";

function App() {
  const [showWelcome, setShowWelcome] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [domains, setDomains] = useState<DiscoveryDomainState[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<number | null>(null);
  const [activeDomainId, setActiveDomainId] = useState<string | null>(null);
  const [workspaceRefresh, setWorkspaceRefresh] = useState(0);
  const [chatPanelWidth, setChatPanelWidth] = useState<string>("45%");
  const splitRef = useRef<HTMLDivElement>(null);
  const draggingSplit = useRef(false);
  const discoveryDone = user?.discovery_complete ?? null;
  const [domainProposals, setDomainProposals] = useState<DiscoveryProposal[]>([]);
  const [acceptedIndices, setAcceptedIndices] = useState<Set<number>>(new Set());
  const [skippedIndices, setSkippedIndices] = useState<Set<number>>(new Set());
  const [proposalLoading, setProposalLoading] = useState(false);

  const loadProjects = useCallback(async () => {
    if (!user) return;
    try {
      const list = await api.listProjects(user.id);
      setProjects(list);
    } catch (err) {
      console.error("Failed to load projects:", err);
    }
  }, [user]);

  const loadDomains = useCallback(async () => {
    if (!user) return;
    try {
      const state = await api.getDiscoveryState(user.id);
      setDomains(state.domains);
    } catch {
      // No domains yet
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
    api.getDiscoveryState(user.id).then((state) => {
      if (!cancelled) setDomains(state.domains);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [user]);

  const handleOnboardingComplete = async () => {
    if (!user) return;
    const updated = await api.getUser(user.id);
    setUser(updated);
    const list = await api.listProjects(updated.id);
    setProjects(list);

    // Load domains (ignore errors - domains may not exist yet)
    try {
      const state = await api.getDiscoveryState(updated.id);
      setDomains(state.domains);
    } catch { /* expected for new users */ }

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
        name: "New task",
      });
      await loadProjects();
      setActiveDomainId(null);
      setActiveProjectId(project.id);
    } catch (err) {
      console.error("Failed to create project:", err);
    }
  };

  const handleSelectProject = (id: number) => {
    setActiveDomainId(null);
    setActiveProjectId(id);
  };

  const handleSelectDomain = (domain: string) => {
    setActiveProjectId(null);
    setActiveDomainId(domain);
  };

  const handleRunComplete = () => {
    setWorkspaceRefresh((k) => k + 1);
  };

  const handleGoHome = () => {
    setActiveDomainId(null);
    setActiveProjectId(null);
  };

  // Reset proposals when domain changes; restore from domain state if proposals exist
  useEffect(() => {
    const domain = domains.find((d) => d.domain === activeDomainId);
    if (domain?.proposed_projects?.length) {
      setDomainProposals(domain.proposed_projects);
    } else {
      setDomainProposals([]);
    }
    setAcceptedIndices(new Set());
    setSkippedIndices(new Set());
  }, [activeDomainId, domains]);

  const handleAcceptProject = useCallback(async (index: number) => {
    if (!user || !activeDomainId) return;
    setProposalLoading(true);
    try {
      await api.acceptDiscoveryProjects(user.id, [index], activeDomainId);
      setAcceptedIndices((prev) => new Set(prev).add(index));
      await loadProjects();
      // Don't navigate away — let the user continue accepting/skipping remaining proposals
    } catch (err) {
      console.error("Failed to accept project:", err);
    }
    setProposalLoading(false);
  }, [user, activeDomainId, loadProjects]);

  const handleAcceptAll = useCallback(async () => {
    if (!user || !activeDomainId) return;
    setProposalLoading(true);
    try {
      const indices = domainProposals.map((_, i) => i);
      const result = await api.acceptDiscoveryProjects(user.id, indices, activeDomainId);
      setAcceptedIndices(new Set(indices));
      await loadProjects();
      loadDomains();
      // Navigate to the first created project after accepting all
      if (result.created_projects?.length > 0) {
        handleSelectProject(result.created_projects[0].id);
      }
    } catch (err) {
      console.error("Failed to accept all projects:", err);
    }
    setProposalLoading(false);
  }, [user, activeDomainId, domainProposals, loadProjects, loadDomains]);

  const handleSkipProject = useCallback((index: number) => {
    setSkippedIndices((prev) => new Set(prev).add(index));
  }, []);

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
  const activeDomain = domains.find((d) => d.domain === activeDomainId);
  const isHome = activeProject?.domain === "home";

  return (
    <div className="app-shell">
      <Sidebar
        projects={projects}
        domains={domains}
        activeProjectId={activeProjectId}
        activeDomainId={activeDomainId}
        onSelectProject={handleSelectProject}
        onSelectDomain={handleSelectDomain}
        onNewProject={handleNewProject}
        onGoHome={handleGoHome}
      />
      <main className="main-content">
        {activeDomain ? (
          <div className="project-split" ref={splitRef}>
            <div className="project-split-chat" style={{ width: chatPanelWidth, minWidth: chatPanelWidth }}>
              <DomainChat
                userId={user.id}
                domain={activeDomain}
                onProposalsReceived={setDomainProposals}
              />
            </div>
            <div className="split-resize-handle" onMouseDown={onSplitMouseDown} />
            <ProposedProjectsPanel
              proposals={domainProposals}
              acceptedIndices={acceptedIndices}
              skippedIndices={skippedIndices}
              onAccept={handleAcceptProject}
              onSkip={handleSkipProject}
              onAcceptAll={handleAcceptAll}
              loading={proposalLoading}
            />
          </div>
        ) : activeProject && !isHome ? (
          <div className="project-split" ref={splitRef}>
            <div className="project-split-chat" style={{ width: chatPanelWidth, minWidth: chatPanelWidth }}>
              <ChatPanel
                project={activeProject}
                userId={user.id}
                onProjectRenamed={loadProjects}
                onRunComplete={handleRunComplete}
                onNavigateDomain={handleSelectDomain}
                onNavigateProject={handleSelectProject}
                onMessageReceived={() => setWorkspaceRefresh((k) => k + 1)}
              />
            </div>
            <div className="split-resize-handle" onMouseDown={onSplitMouseDown} />
            <ProjectWorkspace
              projectId={activeProject.id}
              refreshKey={workspaceRefresh}
            />
          </div>
        ) : (
          <HomeView
            projects={projects}
            domains={domains}
            homeProject={projects.find((p) => p.domain === "home") || null}
            userId={user.id}
            onSelectProject={handleSelectProject}
            onSelectDomain={handleSelectDomain}
            onNewProject={handleNewProject}
            onProjectRenamed={loadProjects}
            onRunComplete={handleRunComplete}
            userName={user.name}
          />
        )}
      </main>
    </div>
  );
}

export default App;
