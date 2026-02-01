import ReactMarkdown from "react-markdown";

interface Props {
  content: string;
}

export function MarkdownArtifact({ content }: Props) {
  return (
    <div className="markdown-artifact">
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  );
}
