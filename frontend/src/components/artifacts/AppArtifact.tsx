import { useState, useEffect, useRef } from "react";

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
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // Get current theme from document
  const getTheme = () => document.documentElement.getAttribute("data-theme") || "light";
  const [theme, setTheme] = useState(getTheme);

  // Listen for theme changes on the document
  useEffect(() => {
    const observer = new MutationObserver(() => {
      const newTheme = getTheme();
      setTheme(newTheme);

      // Send theme update to iframe via postMessage
      if (iframeRef.current?.contentWindow) {
        iframeRef.current.contentWindow.postMessage(
          { type: "envisage-theme-change", theme: newTheme },
          "*"
        );
      }
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });

    return () => observer.disconnect();
  }, []);

  // Serve from backend with theme query param
  const appUrl = `${API_BASE}/app/${artifactId}?theme=${theme}`;

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
        ref={iframeRef}
        src={appUrl}
        title="Custom App"
        className="app-iframe"
      />
    </div>
  );
}
