import { useState } from "react";
import type { ProposalBlock as ProposalBlockType } from "../../services/api";

interface Props {
  block: ProposalBlockType;
  submitted: boolean;
  disabled: boolean;
  onSubmit: (selected: string[], skipped: string[]) => void;
}

export function ProposalBlock({ block, submitted, disabled, onSubmit }: Props) {
  const hasToggleable = block.items.some((item) => item.toggleable);
  const [toggled, setToggled] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    block.items.forEach((item) => {
      init[item.name] = true; // default all enabled
    });
    return init;
  });

  const handleToggle = (name: string) => {
    if (submitted || disabled) return;
    setToggled((prev) => ({ ...prev, [name]: !prev[name] }));
  };

  const handleSubmit = () => {
    const selected = block.items.filter((i) => toggled[i.name]).map((i) => i.name);
    const skipped = block.items.filter((i) => !toggled[i.name]).map((i) => i.name);
    onSubmit(selected, skipped);
  };

  // Group items by tier if tiers exist
  const tiers = new Map<string, typeof block.items>();
  for (const item of block.items) {
    const tier = item.tier || "default";
    if (!tiers.has(tier)) tiers.set(tier, []);
    tiers.get(tier)!.push(item);
  }
  const hasTiers = tiers.size > 1 || !tiers.has("default");

  return (
    <div className={`proposal-block ${submitted ? "submitted" : ""}`}>
      {block.title && <h4 className="proposal-title">{block.title}</h4>}
      {hasTiers ? (
        Array.from(tiers.entries()).map(([tier, items]) => (
          <div key={tier} className="proposal-tier">
            <h5 className="proposal-tier-label">{tier}</h5>
            {items.map((item) => (
              <ProposalCard
                key={item.name}
                item={item}
                toggled={toggled[item.name]}
                onToggle={() => handleToggle(item.name)}
                submitted={submitted}
                disabled={disabled}
              />
            ))}
          </div>
        ))
      ) : (
        block.items.map((item) => (
          <ProposalCard
            key={item.name}
            item={item}
            toggled={toggled[item.name]}
            onToggle={() => handleToggle(item.name)}
            submitted={submitted}
            disabled={disabled}
          />
        ))
      )}
      {hasToggleable && !submitted && (
        <button
          className="proposal-confirm"
          onClick={handleSubmit}
          disabled={disabled}
        >
          Confirm selections
        </button>
      )}
    </div>
  );
}

function ProposalCard({
  item,
  toggled,
  onToggle,
  submitted,
  disabled,
}: {
  item: ProposalBlockType["items"][0];
  toggled: boolean;
  onToggle: () => void;
  submitted: boolean;
  disabled: boolean;
}) {
  return (
    <div className={`proposal-card ${item.highlight ? "highlighted" : ""} ${!toggled ? "skipped" : ""}`}>
      <div className="proposal-card-header">
        <span className="proposal-card-name">{item.name}</span>
        {item.toggleable && !submitted && (
          <button
            className={`proposal-toggle ${toggled ? "enabled" : "disabled"}`}
            onClick={onToggle}
            disabled={disabled}
          >
            {toggled ? "Enabled" : "Skipped"}
          </button>
        )}
      </div>
      {item.highlight && (
        <div className="proposal-highlight">{item.highlight}</div>
      )}
      <p className="proposal-card-desc">{item.description}</p>
      {item.details && Object.keys(item.details).length > 0 && (
        <div className="proposal-card-details">
          {Object.entries(item.details).map(([key, val]) => (
            <div key={key} className="proposal-detail">
              <span className="proposal-detail-key">{key}:</span>
              <span className="proposal-detail-val">{val}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
