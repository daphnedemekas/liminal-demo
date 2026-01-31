import { useState, useRef, useEffect } from "react";
import { api } from "../services/api";
import type { Project } from "../services/api";
import { useRunStream } from "../hooks/useRunStream";

interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: string;
}

interface Props {
  project: Project;
  onProjectRenamed?: () => void;
}

export function ChatPanel({ project, onProjectRenamed }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [hasAutoStarted, setHasAutoStarted] = useState(false);
  const [greetingLoaded, setGreetingLoaded] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { events } = useRunStream(activeRunId);

  // Fetch proactive greeting when project opens
  useEffect(() => {
    if (greetingLoaded || hasAutoStarted) return;

    // For suggested projects with no runs, kick off a full run instead of greeting
    if (project.suggested_by_system && project.run_count === 0) return;

    setGreetingLoaded(true);

    api.getProjectGreeting(project.id).then(({ greeting }) => {
      if (greeting) {
        setMessages([{ role: "assistant", content: greeting }]);
      }
    }).catch(() => {
      // Greeting failed silently — user still sees empty chat
    });
  }, [project.id, greetingLoaded, hasAutoStarted, project.suggested_by_system, project.run_count]);

  // Auto-kick-off for suggested projects that haven't been started yet
  useEffect(() => {
    if (hasAutoStarted) return;
    if (!project.suggested_by_system || project.run_count > 0) return;

    setHasAutoStarted(true);

    const kickoff = async () => {
      setIsRunning(true);
      setMessages([
        {
          role: "system",
          content: `Starting: ${project.name}`,
        },
      ]);

      try {
        const goal =
          `You are working on the project "${project.name}". ` +
          `Context: ${project.description} ` +
          `Start by figuring out what you need to know to be most helpful. ` +
          `Do some initial research or planning, then present what you've found ` +
          `and ask the user what direction they want to go.`;
        const run = await api.createRun(project.id, goal);
        setActiveRunId(run.run_id);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          { role: "system", content: `Failed to start: ${(err as Error).message}` },
        ]);
        setIsRunning(false);
      }
    };

    kickoff();
  }, [project, hasAutoStarted]);

  // Reset state when project changes
  useEffect(() => {
    setMessages([]);
    setActiveRunId(null);
    setIsRunning(false);
    setHasAutoStarted(false);
    setGreetingLoaded(false);
  }, [project.id]);

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
      const tools = (lastEvent.content as Record<string, unknown>)?.tools as Array<Record<string, string>> | undefined;
      const tool = tools?.[0]?.tool;
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
      // Rename project to first user message (truncated) if it's a blank project
      if (!project.suggested_by_system && messages.filter((m) => m.role === "user").length === 0) {
        const shortName = text.length > 60 ? text.slice(0, 57) + "..." : text;
        api.updateProject(project.id, { name: shortName }).then(() => onProjectRenamed?.());
      }
      const run = await api.createRun(project.id, text);
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
        <h3>{project.name}</h3>
        {isRunning && <span className="running-indicator">Working...</span>}
      </div>

      <div className="chat-messages">
        {messages.length === 0 && !isRunning && greetingLoaded && (
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
