import { useState, useEffect, useCallback } from "react";
import { api } from "../services/api";
import type { Artifact, ArtifactContent } from "../services/api";
import { ArtifactCard } from "./artifacts/ArtifactCard";

// Module-level cache so returning to a project shows artifacts instantly
const artifactCache = new Map<number, Artifact[]>();

interface Props {
  projectId: number;
  refreshKey?: number;
}

export function ProjectWorkspace({ projectId, refreshKey }: Props) {
  const [artifacts, setArtifacts] = useState<Artifact[]>(() => artifactCache.get(projectId) || []);
  const [loading, setLoading] = useState(!artifactCache.has(projectId));

  const load = useCallback(async () => {
    try {
      const list = await api.getArtifacts(projectId);
      setArtifacts(list);
      artifactCache.set(projectId, list);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    const cached = artifactCache.get(projectId);
    if (cached) {
      setArtifacts(cached);
      setLoading(false);
    } else {
      setLoading(true);
      setArtifacts([]);
    }
    load();
  }, [projectId, refreshKey, load]);

  const handleUpdate = (id: number, content: ArtifactContent) => {
    setArtifacts((prev) => {
      const updated = prev.map((a) => (a.id === id ? { ...a, content } : a));
      artifactCache.set(projectId, updated);
      return updated;
    });
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
