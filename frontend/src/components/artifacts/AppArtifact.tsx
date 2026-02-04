import { useState } from "react";

export interface AppContent {
  html: string;
  description?: string;
}

interface Props {
  content: AppContent;
  artifactId: number;
}

const API_BASE = import.meta.env.VITE_API_URL || "";

export function AppArtifact({ artifactId }: Props) {
  const [expanded, setExpanded] = useState(false);

  // Serve from backend so apps get the Envisage SDK injected and can use the data API
  const appUrl = `${API_BASE}/app/${artifactId}`;

  return (
    <div className={`app-artifact ${expanded ? "app-expanded" : ""}`}>
      <div className="app-toolbar">
        <button
          className="app-expand-btn"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? "Contract" : "Expand"}
        </button>
      </div>
      <iframe
        src={appUrl}
        title="Custom App"
        className="app-iframe"
      />
    </div>
  );
}
