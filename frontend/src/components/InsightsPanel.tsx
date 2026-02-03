import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { InsightsData } from "../services/api";

const CATEGORY_LABELS: Record<string, string> = {
  bio: "Bio",
  goal: "Goals",
  preference: "Preferences",
  friction: "Frictions",
  value: "Values",
  fact: "Facts",
  decision: "Decisions",
};

const CATEGORY_ORDER = ["bio", "fact", "goal", "value", "preference", "friction", "decision"];

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  if (diff < 60000) return "just now";
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return `${Math.floor(days / 7)}w ago`;
}

export function InsightsPanel({ userId, refreshKey }: { userId: string; refreshKey?: number }) {
  const [data, setData] = useState<InsightsData | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    api.getInsights(userId).then(setData).catch(() => {});
  }, [userId, refreshKey]);

  if (!data || data.total_count === 0) return null;

  const maxCount = Math.max(...data.timeline.map((w) => w.count), 1);

  const orderedCategories = CATEGORY_ORDER.filter((c) => data.categories[c]?.length);

  return (
    <div className="insights-panel">
      <div className="insights-header">
        <span className="section-title" style={{ marginBottom: 0 }}>
          Your insights
        </span>
        <span className="insights-count">{data.total_count}</span>
        <div className="insights-sparkline">
          {data.timeline.map((w, i) => (
            <div
              key={i}
              className="insights-sparkline-bar"
              style={{ height: `${Math.max(4, (w.count / maxCount) * 24)}px` }}
            />
          ))}
        </div>
      </div>

      <div className="insights-pills">
        {orderedCategories.map((cat) => (
          <button
            key={cat}
            className={`insight-pill ${expanded === cat ? "active" : ""}`}
            onClick={() => setExpanded(expanded === cat ? null : cat)}
          >
            {CATEGORY_LABELS[cat] || cat}{" "}
            <span className="insight-pill-count">{data.categories[cat].length}</span>
          </button>
        ))}
      </div>

      {expanded && data.categories[expanded] && (
        <div className="insights-expanded">
          {data.categories[expanded].map((item) => (
            <div key={item.id} className="insight-card">
              <span className="insight-content">{item.content}</span>
              <span className="insight-meta">
                <span className={`insight-source ${item.source_layer === "research" ? "researched" : ""}`}>
                  {item.source_layer === "research" ? "researched" : "from chat"}
                </span>
                <span className="insight-time">{timeAgo(item.created_at)}</span>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
