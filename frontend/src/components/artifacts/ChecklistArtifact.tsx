import type { ChecklistContent } from "../../services/api";
import { api } from "../../services/api";

interface Props {
  artifactId: number;
  projectId: number;
  content: ChecklistContent;
  onUpdate: (content: ChecklistContent) => void;
}

export function ChecklistArtifact({ artifactId, projectId, content, onUpdate }: Props) {
  const toggle = (catIdx: number, itemIdx: number) => {
    const updated = {
      categories: content.categories.map((cat, ci) => ({
        ...cat,
        items: cat.items.map((item, ii) =>
          ci === catIdx && ii === itemIdx ? { ...item, checked: !item.checked } : item
        ),
      })),
    };
    onUpdate(updated);
    api.updateArtifact(projectId, artifactId, updated).catch(() => {});
  };

  const totalItems = content.categories.reduce((sum, c) => sum + c.items.length, 0);
  const checkedItems = content.categories.reduce(
    (sum, c) => sum + c.items.filter((i) => i.checked).length,
    0
  );

  return (
    <div className="checklist-artifact">
      <div className="checklist-progress">
        <div className="checklist-progress-bar">
          <div
            className="checklist-progress-fill"
            style={{ width: totalItems ? `${(checkedItems / totalItems) * 100}%` : "0%" }}
          />
        </div>
        <span className="checklist-progress-text">
          {checkedItems}/{totalItems}
        </span>
      </div>
      {content.categories.map((cat, ci) => (
        <div key={ci} className="checklist-category">
          {content.categories.length > 1 && (
            <div className="checklist-category-name">{cat.name}</div>
          )}
          {cat.items.map((item, ii) => (
            <label key={ii} className={`checklist-item${item.checked ? " checked" : ""}`}>
              <input
                type="checkbox"
                checked={item.checked}
                onChange={() => toggle(ci, ii)}
              />
              <span>{item.text}</span>
            </label>
          ))}
        </div>
      ))}
    </div>
  );
}
