import type { MessageBlock } from "../../services/api";
import { SelectBlock } from "./SelectBlock";
import { InputBlock } from "./InputBlock";
import { ProposalBlock } from "./ProposalBlock";
import { GoalTreeBlock } from "./GoalTreeBlock";
import { ProgressBlock } from "./ProgressBlock";
import { CtaBlock } from "./CtaBlock";

interface Props {
  block: MessageBlock;
  selection: string[];
  submitted: boolean;
  submittedText?: string;
  disabled: boolean;
  onSelect: (values: string[]) => void;
  onSubmit: (text: string) => void;
}

export function BlockRenderer({ block, selection, submitted, submittedText, disabled, onSelect, onSubmit }: Props) {
  switch (block.type) {
    case "select":
      return (
        <SelectBlock
          block={block}
          selection={selection}
          submitted={submitted}
          disabled={disabled}
          onSelect={onSelect}
          onSubmit={(singleValue?: string) => {
            // For single-select, use the directly-passed value to avoid stale closure
            if (singleValue) {
              const label = block.options.find((o) => o.value === singleValue)?.label ?? singleValue;
              onSubmit(label);
            } else {
              // Multi-select: read from selection prop (already up-to-date at submit time)
              const labels = block.options
                .filter((o) => selection.includes(o.value))
                .map((o) => o.label);
              onSubmit(labels.join(", "));
            }
          }}
        />
      );
    case "input":
      return (
        <InputBlock
          block={block}
          submitted={submitted}
          disabled={disabled}
          submittedValue={submittedText}
          onSubmit={(value) => onSubmit(value)}
        />
      );
    case "proposal":
      return (
        <ProposalBlock
          block={block}
          submitted={submitted}
          disabled={disabled}
          onSubmit={(selected, skipped) => {
            const parts: string[] = [];
            if (selected.length) parts.push(`Selected: ${selected.join(", ")}`);
            if (skipped.length) parts.push(`Skipped: ${skipped.join(", ")}`);
            onSubmit(parts.join(". "));
          }}
        />
      );
    case "goal_tree":
      return <GoalTreeBlock block={block} />;
    case "progress":
      return <ProgressBlock block={block} />;
    case "cta":
      return (
        <CtaBlock
          block={block}
          submitted={submitted}
          disabled={disabled}
          onAction={(action) => onSubmit(action)}
        />
      );
    default:
      return null;
  }
}
