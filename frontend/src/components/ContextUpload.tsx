import { useState, useRef, useEffect } from "react";
import { api } from "../services/api";
import type { ContextAttachment } from "../services/api";

interface Props {
  userId: string;
  projectId?: number;
  discoveryDomainId?: number;
  onContextAdded?: (title: string) => void;
}

export function ContextUpload({ userId, projectId, discoveryDomainId, onContextAdded }: Props) {
  const [attachments, setAttachments] = useState<ContextAttachment[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [mode, setMode] = useState<"none" | "url" | "text" | "pdf">("none");
  const [urlInput, setUrlInput] = useState("");
  const [textInput, setTextInput] = useState("");
  const [titleInput, setTitleInput] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.listContext(userId, projectId, discoveryDomainId).then(setAttachments).catch(() => {});
  }, [userId, projectId, discoveryDomainId]);

  const resetForm = () => {
    setMode("none");
    setUrlInput("");
    setTextInput("");
    setTitleInput("");
    setError(null);
  };

  const handleUploadUrl = async () => {
    if (!urlInput.trim()) return;
    setUploading(true);
    setError(null);
    try {
      const att = await api.uploadUrl({ user_id: userId, project_id: projectId, discovery_domain_id: discoveryDomainId, url: urlInput.trim() });
      setAttachments((prev) => [att, ...prev]);
      onContextAdded?.(att.title || att.source_ref || "URL");
      resetForm();
    } catch (e) {
      setError((e as Error).message);
    }
    setUploading(false);
  };

  const handleUploadText = async () => {
    if (!textInput.trim()) return;
    setUploading(true);
    setError(null);
    try {
      const att = await api.uploadText({ user_id: userId, project_id: projectId, discovery_domain_id: discoveryDomainId, title: titleInput || undefined, text: textInput.trim() });
      setAttachments((prev) => [att, ...prev]);
      onContextAdded?.(att.title || "Pasted text");
      resetForm();
    } catch (e) {
      setError((e as Error).message);
    }
    setUploading(false);
  };

  const handleUploadPdf = async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      const att = await api.uploadPdf({ user_id: userId, project_id: projectId, discovery_domain_id: discoveryDomainId, file });
      setAttachments((prev) => [att, ...prev]);
      onContextAdded?.(att.title || file.name);
      resetForm();
    } catch (e) {
      setError((e as Error).message);
    }
    setUploading(false);
  };

  const handleDelete = async (id: number) => {
    try {
      await api.deleteContext(id);
      setAttachments((prev) => prev.filter((a) => a.id !== id));
    } catch (e) {
      console.error("Delete failed:", e);
    }
  };

  const typeIcon = (type: string) => {
    if (type === "url") return "URL";
    if (type === "pdf") return "PDF";
    return "Text";
  };

  return (
    <div className="context-upload">
      <button
        className="context-upload-toggle"
        onClick={() => setExpanded(!expanded)}
      >
        Context {attachments.length > 0 && `(${attachments.length})`}
      </button>

      {expanded && (
        <div className="context-upload-panel">
          {attachments.length > 0 && (
            <div className="context-attachments-list">
              {attachments.map((att) => (
                <div key={att.id} className="context-attachment-item">
                  <span className="context-att-icon">{typeIcon(att.source_type)}</span>
                  <span className="context-att-title">{att.title || att.source_ref || "Untitled"}</span>
                  <button className="context-att-delete" onClick={() => handleDelete(att.id)}>×</button>
                </div>
              ))}
            </div>
          )}

          {mode === "none" && (
            <div className="context-upload-buttons">
              <button onClick={() => setMode("url")}>Add URL</button>
              <button onClick={() => setMode("text")}>Paste text</button>
              <button onClick={() => fileRef.current?.click()}>Upload PDF</button>
              <input
                ref={fileRef}
                type="file"
                accept=".pdf"
                style={{ display: "none" }}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleUploadPdf(f);
                  e.target.value = "";
                }}
              />
            </div>
          )}

          {mode === "url" && (
            <div className="context-upload-form">
              <input
                type="url"
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                placeholder="https://..."
                autoFocus
                onKeyDown={(e) => e.key === "Enter" && handleUploadUrl()}
              />
              <div className="context-form-actions">
                <button onClick={handleUploadUrl} disabled={uploading || !urlInput.trim()}>
                  {uploading ? "Fetching..." : "Add"}
                </button>
                <button onClick={resetForm} className="context-cancel">Cancel</button>
              </div>
            </div>
          )}

          {mode === "text" && (
            <div className="context-upload-form">
              <input
                type="text"
                value={titleInput}
                onChange={(e) => setTitleInput(e.target.value)}
                placeholder="Title (optional)"
              />
              <textarea
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                placeholder="Paste your text here..."
                rows={4}
                autoFocus
              />
              <div className="context-form-actions">
                <button onClick={handleUploadText} disabled={uploading || !textInput.trim()}>
                  {uploading ? "Saving..." : "Add"}
                </button>
                <button onClick={resetForm} className="context-cancel">Cancel</button>
              </div>
            </div>
          )}

          {error && <div className="context-upload-error">{error}</div>}
        </div>
      )}
    </div>
  );
}
