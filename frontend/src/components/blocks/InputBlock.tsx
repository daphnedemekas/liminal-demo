import { useState } from "react";
import type { InputBlock as InputBlockType } from "../../services/api";

interface Props {
  block: InputBlockType;
  submitted: boolean;
  disabled: boolean;
  submittedValue?: string;
  onSubmit: (value: string) => void;
}

export function InputBlock({ block, submitted, disabled, submittedValue, onSubmit }: Props) {
  const [value, setValue] = useState("");

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || submitted || disabled) return;
    onSubmit(trimmed);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  if (submitted) {
    return (
      <div className="input-block submitted">
        <p className="input-prompt">{block.prompt}</p>
        <div className="input-submitted-value">{submittedValue || value}</div>
      </div>
    );
  }

  return (
    <div className="input-block">
      <p className="input-prompt">{block.prompt}</p>
      <textarea
        className="input-textarea"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={block.placeholder || ""}
        disabled={disabled}
        rows={3}
      />
      <button
        className="input-continue"
        onClick={handleSubmit}
        disabled={disabled || !value.trim()}
      >
        Continue
      </button>
    </div>
  );
}
