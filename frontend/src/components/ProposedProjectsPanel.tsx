import type { DiscoveryProposal } from "../services/api";

interface Props {
  proposals: DiscoveryProposal[];
  acceptedIndices: Set<number>;
  skippedIndices: Set<number>;
  onAccept: (index: number) => void;
  onSkip: (index: number) => void;
  onAcceptAll: () => void;
  loading: boolean;
}

export function ProposedProjectsPanel({
  proposals,
  acceptedIndices,
  skippedIndices,
  onAccept,
  onSkip,
  onAcceptAll,
  loading,
}: Props) {
  if (proposals.length === 0) {
    return (
      <div className="proposed-projects-panel">
        <div className="workspace-empty">
          <p className="workspace-empty-title">Proposed projects</p>
          <p className="workspace-empty-hint">
            Projects will appear here as we talk
          </p>
        </div>
      </div>
    );
  }

  const hasUnhandled = proposals.some(
    (_, i) => !acceptedIndices.has(i) && !skippedIndices.has(i)
  );

  return (
    <div className="proposed-projects-panel">
      <div className="workspace-header">
        <h3>Proposed Projects</h3>
        <span className="workspace-count">{proposals.length} proposals</span>
      </div>
      <div className="proposed-projects-list">
        {proposals.map((p, i) => {
          const accepted = acceptedIndices.has(i);
          const skipped = skippedIndices.has(i);
          const cls = `proposal-card${accepted ? " accepted" : ""}${skipped ? " skipped" : ""}`;
          return (
            <div key={i} className={cls}>
              <div className="proposal-card-header">
                {accepted && <span className="proposal-check">&#10003;</span>}
                <h4>{p.name}</h4>
              </div>
              <p className="proposal-desc">{p.description}</p>
              {p.first_goal && (
                <p className="proposal-meta">
                  <strong>First step:</strong> {p.first_goal}
                </p>
              )}
              {p.success_metric && (
                <p className="proposal-meta">
                  <strong>Tracking:</strong> {p.success_metric}
                  {p.metric_target ? ` — ${p.metric_target}` : ""}
                </p>
              )}
              {!accepted && !skipped && (
                <div className="proposal-actions">
                  <button
                    className="proposal-accept-btn"
                    onClick={() => onAccept(i)}
                    disabled={loading}
                  >
                    Accept
                  </button>
                  <button
                    className="proposal-skip-btn"
                    onClick={() => onSkip(i)}
                    disabled={loading}
                  >
                    Skip
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
      {hasUnhandled && (
        <button
          className="proposal-accept-all-btn"
          onClick={onAcceptAll}
          disabled={loading}
        >
          Accept All
        </button>
      )}
    </div>
  );
}
