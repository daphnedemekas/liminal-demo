import type { CtaBlock as CtaBlockType } from "../../services/api";

interface Props {
  block: CtaBlockType;
  submitted: boolean;
  disabled: boolean;
  onAction: (action: string) => void;
}

export function CtaBlock({ block, submitted, disabled, onAction }: Props) {
  return (
    <div className={`cta-block ${submitted ? "submitted" : ""}`}>
      <button
        className="cta-primary"
        onClick={() => onAction(block.primary.action)}
        disabled={submitted || disabled}
      >
        {block.primary.label}
      </button>
      {block.secondary && (
        <button
          className="cta-secondary"
          onClick={() => onAction(block.secondary!.action)}
          disabled={submitted || disabled}
        >
          {block.secondary.label}
        </button>
      )}
      {block.note && <p className="cta-note">{block.note}</p>}
    </div>
  );
}
