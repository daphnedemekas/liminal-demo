import type { VideoCollectionContent } from "../../services/api";

interface Props {
  content: VideoCollectionContent;
}

function youtubeId(url: string): string | null {
  const m =
    url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&?/]+)/) ||
    url.match(/youtube\.com\/shorts\/([^&?/]+)/);
  return m ? m[1] : null;
}

export function VideoArtifact({ content }: Props) {
  return (
    <div className="video-artifact">
      {content.videos.map((video, i) => {
        const vid = youtubeId(video.url);
        return (
          <div key={i} className="video-item">
            {vid ? (
              <div className="video-embed">
                <iframe
                  src={`https://www.youtube.com/embed/${vid}`}
                  title={video.title}
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                />
              </div>
            ) : (
              <a href={video.url} target="_blank" rel="noopener noreferrer" className="video-link">
                {video.title}
              </a>
            )}
            <div className="video-info">
              <div className="video-title">{video.title}</div>
              {video.description && (
                <div className="video-desc">{video.description}</div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
