import type { SelectBlock as SelectBlockType } from "../../services/api";

interface Props {
  block: SelectBlockType;
  selection: string[];
  submitted: boolean;
  disabled: boolean;
  onSelect: (values: string[]) => void;
  onSubmit: (singleValue?: string) => void;
}

export function SelectBlock({ block, selection, submitted, disabled, onSelect, onSubmit }: Props) {
  // Some blocks (like metric/notification choices before CTA) shouldn't auto-submit
  const shouldAutoSubmit = block.submitOnSelect !== false;

  const handleOptionClick = (value: string) => {
    if (submitted || disabled) return;
    if (block.multi) {
      const next = selection.includes(value)
        ? selection.filter((v) => v !== value)
        : [...selection, value];
      onSelect(next);
    } else {
      onSelect([value]);
      // Single-select auto-submits unless submitOnSelect is false
      if (shouldAutoSubmit) {
        setTimeout(() => onSubmit(value), 50);
      }
    }
  };

  return (
    <div className={`select-block ${submitted ? "submitted" : ""}`}>
      {block.prompt && <p className="select-prompt">{block.prompt}</p>}
      <div className="select-options">
        {block.options.map((opt) => {
          const isSelected = selection.includes(opt.value);
          return (
            <button
              key={opt.value}
              className={`select-option ${isSelected ? "selected" : ""} ${submitted ? "submitted" : ""}`}
              onClick={() => handleOptionClick(opt.value)}
              disabled={submitted || disabled}
            >
              {block.multi && (
                <span className="select-checkbox">
                  {isSelected ? "☑" : "☐"}
                </span>
              )}
              <span className="select-option-label">{opt.label}</span>
              {opt.description && (
                <span className="select-option-desc">{opt.description}</span>
              )}
            </button>
          );
        })}
      </div>
      {block.multi && !submitted && selection.length > 0 && (
        <button
          className="select-continue"
          onClick={onSubmit}
          disabled={disabled}
        >
          Continue
        </button>
      )}
    </div>
  );
}
