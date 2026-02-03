import { useState, useEffect } from "react";
import { api } from "../services/api";
import type { DomainOption } from "../services/api";

interface Props {
  userId: string;
  userName: string;
  onComplete: () => void;
}

const ICON_MAP: Record<string, string> = {
  briefcase: "",
  users: "",
  book: "",
  heart: "",
  palette: "",
  dollar: "",
  brain: "",
};

export function DiscoveryView({ userId, userName, onComplete }: Props) {
  const [options, setOptions] = useState<DomainOption[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.getDiscoveryOptions().then(setOptions);
  }, []);

  const toggleOption = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleSelectDomains = async () => {
    if (selected.size === 0) return;
    setLoading(true);
    try {
      await api.selectDomains(userId, [...selected]);
      await api.completeDiscovery(userId);
      onComplete();
    } catch (err) {
      console.error("Failed to select domains:", err);
      setLoading(false);
    }
  };

  const handleSkipAll = async () => {
    setLoading(true);
    try {
      await api.completeDiscovery(userId);
      onComplete();
    } catch (err) {
      console.error("Failed to skip:", err);
      setLoading(false);
    }
  };

  return (
    <div className="onboarding-view">
      <div className="onboarding-container">
        <div className="onboarding-header">
          <h1>Hi {userName}!</h1>
          <p>Where in your life do you wish you had more agency?</p>
          <p className="onboarding-hint">Select the areas where AI agents could help</p>
        </div>

        <div className="context-grid">
          {options.map((opt) => (
            <button
              key={opt.id}
              className={`context-option ${selected.has(opt.id) ? "selected" : ""}`}
              onClick={() => toggleOption(opt.id)}
            >
              <span className="context-icon">{ICON_MAP[opt.icon] || ""}</span>
              <span className="context-label">{opt.label}</span>
            </button>
          ))}
        </div>

        <div className="onboarding-actions">
          <button
            className="onboarding-primary"
            onClick={handleSelectDomains}
            disabled={selected.size === 0 || loading}
          >
            {loading ? "Setting up..." : "Let's go"}
          </button>
          <button className="onboarding-skip" onClick={handleSkipAll} disabled={loading}>
            Skip for now
          </button>
        </div>
      </div>
    </div>
  );
}
