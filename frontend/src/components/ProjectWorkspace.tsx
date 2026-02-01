import { useState, useEffect, useCallback } from "react";
import { api } from "../services/api";
import type { Artifact, ArtifactContent } from "../services/api";
import { ArtifactCard } from "./artifacts/ArtifactCard";

interface Props {
  projectId: number;
  refreshKey?: number;
}

export function ProjectWorkspace({ projectId, refreshKey }: Props) {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const list = await api.getArtifacts(projectId);
      setArtifacts(list);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    setLoading(true);
    setArtifacts([]);
    load();
  }, [projectId, refreshKey, load]);

  const handleUpdate = (id: number, content: ArtifactContent) => {
    setArtifacts((prev) =>
      prev.map((a) => (a.id === id ? { ...a, content } : a))
    );
  };

  if (loading) {
    return (
      <div className="workspace">
        <div className="workspace-empty">Loading...</div>
      </div>
    );
  }

  if (artifacts.length === 0) {
    return (
      <div className="workspace">
        <div className="workspace-empty">
          <p className="workspace-empty-title">No content yet</p>
          <p className="workspace-empty-hint">
            Chat with the assistant to generate a plan, schedule, resources, or other content for this project.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="workspace">
      <div className="workspace-header">
        <h3>Workspace</h3>
        <span className="workspace-count">{artifacts.length} items</span>
      </div>
      <div className="workspace-cards">
        {artifacts.map((a) => (
          <ArtifactCard
            key={a.id}
            artifact={a}
            projectId={projectId}
            onUpdate={handleUpdate}
          />
        ))}
      </div>
    </div>
  );
}
