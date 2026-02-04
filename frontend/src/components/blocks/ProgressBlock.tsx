import type { ProgressBlock as ProgressBlockType } from "../../services/api";

interface Props {
  block: ProgressBlockType;
}

export function ProgressBlock({ block }: Props) {
  const statusIcon = (status: string) => {
    switch (status) {
      case "done": return "✓";
      case "in_progress": return "◐";
      case "pending": return "○";
      default: return "○";
    }
  };

  return (
    <div className="progress-block">
      {block.steps.map((step, i) => (
        <div key={i} className={`progress-step ${step.status}`}>
          <span className="progress-icon">{statusIcon(step.status)}</span>
          <span className="progress-label">{step.label}</span>
          {step.detail && (
            <span className="progress-detail">{step.detail}</span>
          )}
        </div>
      ))}
    </div>
  );
}
