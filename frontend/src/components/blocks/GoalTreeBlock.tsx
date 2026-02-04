import type { GoalTreeBlock as GoalTreeBlockType } from "../../services/api";

interface Props {
  block: GoalTreeBlockType;
}

export function GoalTreeBlock({ block }: Props) {
  return (
    <div className="goal-tree-block">
      <div className="goal-tree-root">{block.root}</div>
      <div className="goal-tree-branches">
        {block.branches.map((branch) => (
          <div
            key={branch.label}
            className={`goal-tree-branch ${branch.flagged ? "flagged" : ""}`}
          >
            <div className="goal-tree-branch-label">
              {branch.label}
              {branch.flagged && <span className="goal-tree-flag">← focus here</span>}
            </div>
            <ul className="goal-tree-items">
              {branch.items.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
