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

// Demo progress data for Olivia's three main projects
const DEMO_PROGRESS = {
  career: {
    label: "Career Transition",
    icon: "💼",
    color: "#4a8fe7",
    progress: 47,
    trend: [25, 32, 38, 42, 44, 47],
    stats: [
      { label: "Skills", value: "5/8", trend: "up" },
      { label: "Network", value: "8", trend: "up" },
      { label: "Portfolio", value: "3", trend: "same" },
    ],
    insight: "On track for 12-week goal. Figma skills improving fastest.",
  },
  health: {
    label: "Gluten-Free Journey",
    icon: "🌿",
    color: "#34c759",
    progress: 85,
    trend: [60, 68, 75, 78, 82, 85],
    stats: [
      { label: "Streak", value: "18d", trend: "up" },
      { label: "Energy", value: "8.2", trend: "up" },
      { label: "Meals", value: "47", trend: "up" },
    ],
    insight: "Energy levels up 15% since starting. Keep it up!",
  },
  guitar: {
    label: "Guitar Learning",
    icon: "🎸",
    color: "#f0a030",
    progress: 65,
    trend: [20, 35, 45, 52, 58, 65],
    stats: [
      { label: "Chords", value: "8", trend: "up" },
      { label: "Songs", value: "5", trend: "up" },
      { label: "Streak", value: "14d", trend: "up" },
    ],
    insight: "G-C-D progression mastered! Ready for barre chords.",
  },
};

// SVG Progress Ring Component
function ProgressRing({ progress, color, size = 64 }: { progress: number; color: string; size?: number }) {
  const strokeWidth = 6;
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (progress / 100) * circumference;

  return (
    <svg width={size} height={size} className="progress-ring">
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="var(--border-hairline)"
        strokeWidth={strokeWidth}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: "stroke-dashoffset 0.5s ease" }}
      />
      <text
        x="50%"
        y="50%"
        textAnchor="middle"
        dy=".3em"
        fill="var(--text-primary)"
        fontSize="14"
        fontWeight="600"
      >
        {progress}%
      </text>
    </svg>
  );
}

// Mini Trend Line Component (like Oura)
function TrendLine({ data, color, height = 32 }: { data: number[]; color: string; height?: number }) {
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const width = 80;
  const padding = 2;

  const points = data.map((val, i) => {
    const x = padding + (i / (data.length - 1)) * (width - 2 * padding);
    const y = height - padding - ((val - min) / range) * (height - 2 * padding);
    return `${x},${y}`;
  }).join(" ");

  return (
    <svg width={width} height={height} className="trend-line">
      <defs>
        <linearGradient id={`grad-${color.replace('#', '')}`} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
      {/* Fill under the line */}
      <polygon
        fill={`url(#grad-${color.replace('#', '')})`}
        points={`${padding},${height - padding} ${points} ${width - padding},${height - padding}`}
      />
    </svg>
  );
}

// Stat Badge Component
function StatBadge({ label, value, trend }: { label: string; value: string; trend: string }) {
  const trendIcon = trend === "up" ? "↑" : trend === "down" ? "↓" : "→";
  const trendColor = trend === "up" ? "#34c759" : trend === "down" ? "#e54d4d" : "var(--text-muted)";

  return (
    <div className="stat-badge">
      <span className="stat-badge-value">{value}</span>
      <span className="stat-badge-label">{label}</span>
      <span className="stat-badge-trend" style={{ color: trendColor }}>{trendIcon}</span>
    </div>
  );
}

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
  const [showProgress, setShowProgress] = useState(true);

  useEffect(() => {
    api.getInsights(userId).then(setData).catch(() => {});
  }, [userId, refreshKey]);

  const maxCount = data ? Math.max(...data.timeline.map((w) => w.count), 1) : 1;
  const orderedCategories = data ? CATEGORY_ORDER.filter((c) => data.categories[c]?.length) : [];

  return (
    <div className="insights-panel">
      {/* Progress Overview Section - Oura-style */}
      <div className="insights-header">
        <span className="section-title" style={{ marginBottom: 0 }}>
          Olivia's Progress
        </span>
        <button
          className="toggle-progress-btn"
          onClick={() => setShowProgress(!showProgress)}
        >
          {showProgress ? "Hide" : "Show"}
        </button>
      </div>

      {showProgress && (
        <div className="progress-cards">
          {Object.entries(DEMO_PROGRESS).map(([key, project]) => (
            <div key={key} className="progress-card" style={{ borderLeftColor: project.color }}>
              <div className="progress-card-header">
                <span className="progress-card-icon">{project.icon}</span>
                <span className="progress-card-label">{project.label}</span>
              </div>

              <div className="progress-card-content">
                <div className="progress-ring-container">
                  <ProgressRing progress={project.progress} color={project.color} />
                </div>

                <div className="progress-card-right">
                  <div className="trend-container">
                    <TrendLine data={project.trend} color={project.color} />
                    <span className="trend-label">6 weeks</span>
                  </div>

                  <div className="stats-row">
                    {project.stats.map((stat, i) => (
                      <StatBadge key={i} {...stat} />
                    ))}
                  </div>
                </div>
              </div>

              <div className="progress-card-insight">
                <span className="insight-icon">💡</span>
                <span>{project.insight}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Insights Section */}
      {data && data.total_count > 0 && (
        <>
          <div className="insights-header" style={{ marginTop: 16 }}>
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
        </>
      )}
    </div>
  );
}
