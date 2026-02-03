import { useState } from "react";

export interface AppContent {
  html: string;
  description?: string;
}

interface Props {
  content: AppContent;
}

export function AppArtifact({ content }: Props) {
  const [expanded, setExpanded] = useState(false);

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
        srcDoc={content.html}
        sandbox="allow-scripts"
        title="Custom App"
        className="app-iframe"
      />
    </div>
  );
}
