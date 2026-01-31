import { useState, useRef, useEffect } from "react";
import { api } from "../services/api";
import { useRunStream } from "../hooks/useRunStream";

interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: string;
}

interface Props {
  projectId: number;
  projectName: string;
  onProjectRenamed?: () => void;
}

export function ChatPanel({ projectId, projectName, onProjectRenamed }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { events, status } = useRunStream(activeRunId);

  // Process streaming events into messages
  useEffect(() => {
    if (events.length === 0) return;
    const lastEvent = events[events.length - 1];

    if (lastEvent.type === "event" && lastEvent.event_type === "assistant") {
      const text = (lastEvent.content as Record<string, string>)?.text;
      if (text) {
        setMessages((prev) => {
          // Update last assistant message or add new one
          const last = prev[prev.length - 1];
          if (last?.role === "assistant") {
            return [...prev.slice(0, -1), { ...last, content: text }];
          }
          return [...prev, { role: "assistant", content: text }];
        });
      }
    }

    if (lastEvent.type === "event" && lastEvent.event_type === "tool_use") {
      const tool = (lastEvent.content as Record<string, string>)?.tool;
      setMessages((prev) => [
        ...prev,
        { role: "system", content: `Using tool: ${tool}` },
      ]);
    }

    if (lastEvent.type === "event" && lastEvent.event_type === "result") {
      const text = (lastEvent.content as Record<string, string>)?.text;
      if (text) {
        setMessages((prev) => [...prev, { role: "assistant", content: text }]);
      }
      setIsRunning(false);
      setActiveRunId(null);
    }

    if (lastEvent.type === "status" && lastEvent.status === "done") {
      if (lastEvent.result_summary) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: lastEvent.result_summary! },
        ]);
      }
      setIsRunning(false);
      setActiveRunId(null);
    }

    if (lastEvent.type === "error") {
      setMessages((prev) => [
        ...prev,
        { role: "system", content: `Error: ${lastEvent.error}` },
      ]);
      setIsRunning(false);
      setActiveRunId(null);
    }
  }, [events]);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || isRunning) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setIsRunning(true);

    try {
      // Rename project to first message (truncated)
      if (messages.length === 0) {
        const shortName = text.length > 60 ? text.slice(0, 57) + "..." : text;
        api.updateProject(projectId, { name: shortName }).then(() => onProjectRenamed?.());
      }
      const run = await api.createRun(projectId, text);
      setActiveRunId(run.run_id);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "system", content: `Failed to start: ${(err as Error).message}` },
      ]);
      setIsRunning(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <h3>{projectName}</h3>
        {isRunning && <span className="running-indicator">Working...</span>}
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="empty-chat">
            <p className="prompt">What would you like help with?</p>
            <p className="hint">
              Try: "Compare the top 5 project management tools" or "Research kitchen backsplash options under $800"
            </p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            <div className="message-content">
              {msg.role === "system" ? (
                <em>{msg.content}</em>
              ) : (
                msg.content
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-area">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isRunning ? "Agent is working..." : "Tell me what you need..."}
          disabled={isRunning}
          rows={1}
        />
        <button onClick={handleSend} disabled={isRunning || !input.trim()}>
          Send
        </button>
      </div>
    </div>
  );
}
