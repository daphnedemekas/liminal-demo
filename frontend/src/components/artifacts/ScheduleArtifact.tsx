import type { ScheduleContent } from "../../services/api";

interface Props {
  content: ScheduleContent;
}

export function ScheduleArtifact({ content }: Props) {
  // Group entries by day
  const days = new Map<string, typeof content.entries>();
  for (const entry of content.entries) {
    if (!days.has(entry.day)) days.set(entry.day, []);
    days.get(entry.day)!.push(entry);
  }

  return (
    <div className="schedule-artifact">
      {[...days.entries()].map(([day, entries]) => (
        <div key={day} className="schedule-day">
          <div className="schedule-day-name">{day}</div>
          <div className="schedule-entries">
            {entries.map((entry, i) => (
              <div key={i} className="schedule-entry">
                <span className="schedule-time">{entry.time_block}</span>
                <span className="schedule-activity">{entry.activity}</span>
                {entry.notes && (
                  <span className="schedule-notes">{entry.notes}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
