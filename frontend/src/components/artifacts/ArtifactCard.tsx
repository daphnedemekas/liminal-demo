import type {
  Artifact,
  ChecklistContent,
  VideoCollectionContent,
  ResourceListContent,
  ScheduleContent,
  ArtifactContent,
} from "../../services/api";
import { ChecklistArtifact } from "./ChecklistArtifact";
import { VideoArtifact } from "./VideoArtifact";
import { ResourceArtifact } from "./ResourceArtifact";
import { ScheduleArtifact } from "./ScheduleArtifact";
import { MarkdownArtifact } from "./MarkdownArtifact";

interface Props {
  artifact: Artifact;
  projectId: number;
  onUpdate: (id: number, content: ArtifactContent) => void;
}

export function ArtifactCard({ artifact, projectId, onUpdate }: Props) {
  const { artifact_type, title, content } = artifact;

  const renderContent = () => {
    switch (artifact_type) {
      case "checklist":
        return (
          <ChecklistArtifact
            artifactId={artifact.id}
            projectId={projectId}
            content={content as ChecklistContent}
            onUpdate={(c) => onUpdate(artifact.id, c)}
          />
        );
      case "video_collection":
        return <VideoArtifact content={content as VideoCollectionContent} />;
      case "resource_list":
        return <ResourceArtifact content={content as ResourceListContent} />;
      case "schedule":
        return <ScheduleArtifact content={content as ScheduleContent} />;
      default: {
        const md = typeof content === "string"
          ? content
          : ((content as Record<string, unknown>)?.markdown as string) || JSON.stringify(content, null, 2);
        return <MarkdownArtifact content={md} />;
      }
    }
  };

  return (
    <div className={`workspace-card card-${artifact_type}`}>
      <div className="workspace-card-header">
        <span className="workspace-card-type">{artifact_type.replace(/_/g, " ")}</span>
        <span className="workspace-card-title">{title}</span>
      </div>
      <div className="workspace-card-body">{renderContent()}</div>
      {artifact.sources?.length > 0 && (
        <div className="workspace-card-sources">
          {artifact.sources.map((s, i) => (
            <a key={i} href={s.url} target="_blank" rel="noopener noreferrer">
              {new URL(s.url).hostname}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
