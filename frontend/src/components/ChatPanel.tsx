import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "../services/api";
import type { Project, ChatAction, SynthesisEvent, SynthesisArtifact } from "../services/api";
import { useRunStream } from "../hooks/useRunStream";
import { useAudio } from "../hooks/useAudio";

interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  actions?: ChatAction[];
  timestamp?: string;
  synthesis?: SynthesisEvent;
}

interface Props {
  project: Project;
  onProjectRenamed?: () => void;
}

interface ActivityEntry {
  type: "tool" | "text";
  tool?: string;
  detail?: string;
  text?: string;
  timestamp: number;
}

function formatToolActivity(tool: string, input: Record<string, unknown>): string {
  switch (tool) {
    case "WebSearch":
    case "web_search":
      return `Searching: "${input.query || input.search_query || ""}"`;
    case "WebFetch":
    case "web_fetch":
      return `Reading: ${input.url || ""}`;
    case "Read":
      return `Reading file: ${input.file_path || input.path || ""}`;
    case "Write":
      return `Writing file: ${input.file_path || input.path || ""}`;
    case "Edit":
      return `Editing: ${input.file_path || input.path || ""}`;
    case "Bash":
      return `Running: ${String(input.command || "").slice(0, 80)}`;
    case "Glob":
      return `Finding files: ${input.pattern || ""}`;
    case "Grep":
      return `Searching code: "${input.pattern || ""}"`;
    default:
      return `Using ${tool}`;
  }
}

export function ChatPanel({ project, onProjectRenamed }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isChatting, setIsChatting] = useState(false);
  const [hasAutoStarted, setHasAutoStarted] = useState(false);
  const [greetingLoaded, setGreetingLoaded] = useState(false);
  const [activityLog, setActivityLog] = useState<ActivityEntry[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { events, synthesis } = useRunStream(activeRunId);
  const [showFullOutput, setShowFullOutput] = useState(false);
  const {
    isAudioMode, isRecording, isPlaying, transcript,
    toggleAudioMode, startRecording, stopRecording, playTTS, stopAudio,
  } = useAudio();

  const sendChat = useCallback(async (text: string | undefined) => {
    if (isChatting || isRunning) return;

    if (text) {
      setMessages((prev) => [...prev, { role: "user", content: text }]);
    }
    setIsChatting(true);

    try {
      const res = await api.sendChat(project.id, text);

      if (res.message) {
        setMessages((prev) => {
          // Deduplicate: skip if last message is identical assistant text
          const last = prev[prev.length - 1];
          if (last?.role === "assistant" && last.content === res.message) {
            return prev;
          }
          return [
            ...prev,
            { role: "assistant", content: res.message, actions: res.actions },
          ];
        });
        // Auto-play TTS in audio mode
        if (isAudioMode) {
          playTTS(res.message);
        }
      }

      if (res.run_id) {
        setIsRunning(true);
        setActiveRunId(res.run_id);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "system", content: `Error: ${(err as Error).message}` },
      ]);
    } finally {
      setIsChatting(false);
    }
  }, [project.id, isChatting, isRunning]);

  // Load chat history on project open, then greet if no history
  useEffect(() => {
    if (greetingLoaded || hasAutoStarted) return;

    // For suggested projects with no runs, kick off via chat instead
    if (project.suggested_by_system && project.run_count === 0) return;

    setGreetingLoaded(true);

    const load = async () => {
      try {
        const history = await api.getMessages(project.id);
        if (history.length > 0) {
          setMessages(history.map((m) => ({
            role: m.role as Message["role"],
            content: m.content,
            actions: m.actions,
            timestamp: m.created_at,
          })));
          return; // history loaded, no greeting needed
        }
      } catch {
        // fall through to greeting
      }
      sendChat(undefined);
    };
    load();
  }, [project.id, greetingLoaded, hasAutoStarted, project.suggested_by_system, project.run_count, sendChat]);

  // Auto-kick-off for suggested projects that haven't been started yet
  useEffect(() => {
    if (hasAutoStarted) return;
    if (!project.suggested_by_system || project.run_count > 0) return;

    setHasAutoStarted(true);
    setGreetingLoaded(true);

    const kickoff = async () => {
      setMessages([
        { role: "system", content: `Starting: ${project.name}` },
      ]);

      const goal =
        `You are working on the project "${project.name}". ` +
        `Context: ${project.description} ` +
        `Start by figuring out what you need to know to be most helpful. ` +
        `Do some initial research or planning, then present what you've found ` +
        `and ask the user what direction they want to go.`;

      sendChat(goal);
    };

    kickoff();
  }, [project, hasAutoStarted, sendChat]);

  // Reset state when project changes
  useEffect(() => {
    setMessages([]);
    setActiveRunId(null);
    setIsRunning(false);
    setIsChatting(false);
    setHasAutoStarted(false);
    setGreetingLoaded(false);
    setActivityLog([]);
  }, [project.id]);

  // Process streaming events into messages
  useEffect(() => {
    if (events.length === 0) return;
    const lastEvent = events[events.length - 1];

    if (lastEvent.type === "event" && lastEvent.event_type === "assistant") {
      const text = (lastEvent.content as Record<string, string>)?.text;
      if (text) {
        setActivityLog((prev) => {
          const last = prev[prev.length - 1];
          if (last?.type === "text") {
            return [...prev.slice(0, -1), { ...last, text }];
          }
          return [...prev, { type: "text", text, timestamp: Date.now() }];
        });
      }
    }

    if (lastEvent.type === "event" && lastEvent.event_type === "tool_use") {
      const tools = (lastEvent.content as Record<string, unknown>)?.tools as Array<Record<string, unknown>> | undefined;
      if (tools?.[0]) {
        const tool = tools[0].tool as string;
        const toolInput = tools[0].input as Record<string, unknown> || {};
        const detail = formatToolActivity(tool, toolInput);
        setActivityLog((prev) => [...prev, { type: "tool", tool, detail, timestamp: Date.now() }]);
      }
    }

    if (lastEvent.type === "event" && lastEvent.event_type === "result") {
      const text = (lastEvent.content as Record<string, string>)?.text;
      if (text) {
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant" && last.content === text) return prev;
          return [...prev, { role: "assistant", content: text }];
        });
      }
      setActivityLog([]);
      setIsRunning(false);
      setActiveRunId(null);
    }

    if (lastEvent.type === "status" && lastEvent.status === "done") {
      setActivityLog([]);
      setIsRunning(false);
      setShowFullOutput(false);
      setActiveRunId(null);
    }

    if (lastEvent.type === "error") {
      setMessages((prev) => [
        ...prev,
        { role: "system", content: `Error: ${lastEvent.error}` },
      ]);
      setActivityLog([]);
      setIsRunning(false);
      setActiveRunId(null);
    }
  }, [events]);

  // Handle synthesis event — display personalized summary instead of raw output
  useEffect(() => {
    if (!synthesis) return;

    // Add the synthesis summary as an assistant message with actions
    setMessages((prev) => {
      // Remove any raw result message that might have been added
      const filtered = prev.filter(
        (m) => !(m.role === "assistant" && m.content === synthesis.full_output)
      );
      return [
        ...filtered,
        {
          role: "assistant",
          content: synthesis.summary,
          actions: synthesis.actions,
          synthesis: synthesis,
        },
      ];
    });

    setActivityLog([]);
    setIsRunning(false);
    setActiveRunId(null);
  }, [synthesis]);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activityLog]);

  // When recording stops and we have a transcript, send it
  const lastTranscriptRef = useRef("");
  useEffect(() => {
    if (!isRecording && transcript && transcript !== lastTranscriptRef.current) {
      lastTranscriptRef.current = transcript;
      sendChat(transcript);
    }
  }, [isRecording, transcript, sendChat]);

  const handleMicClick = () => {
    if (isPlaying) {
      stopAudio();
      return;
    }
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || isRunning || isChatting) return;

    setInput("");

    // Rename project to first user message if it's a blank project
    if (!project.suggested_by_system && messages.filter((m) => m.role === "user").length === 0) {
      const shortName = text.length > 60 ? text.slice(0, 57) + "..." : text;
      api.updateProject(project.id, { name: shortName }).then(() => onProjectRenamed?.());
    }

    sendChat(text);
  };

  const handleActionClick = (actionText: string) => {
    if (isRunning || isChatting) return;
    sendChat(actionText);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const busy = isRunning || isChatting;

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <h3>{project.name}</h3>
        <div className="chat-header-right">
          {isRunning && <span className="running-indicator">Working...</span>}
          {isChatting && !isRunning && <span className="running-indicator">Thinking...</span>}
          <button
            className={`audio-mode-toggle${isAudioMode ? " active" : ""}`}
            onClick={toggleAudioMode}
            title={isAudioMode ? "Disable auto-speak" : "Enable auto-speak"}
          >
            {isAudioMode ? "🔊 Voice" : "🔇 Voice"}
          </button>
        </div>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && !busy && greetingLoaded && (
          <div className="empty-chat">
            <p className="prompt">What would you like help with?</p>
            <p className="hint">
              Try: "Compare the top 5 project management tools" or "Research kitchen backsplash options under $800"
            </p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i}>
            <div className={`message ${msg.role}`}>
              <div className="message-content">
                {msg.role === "system" ? (
                  <em>{msg.content}</em>
                ) : (
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                )}
              </div>
              {msg.synthesis && (
                <>
                  {msg.synthesis.artifacts.length > 0 && (
                    <div className="synthesis-artifacts">
                      {msg.synthesis.artifacts.map((art: SynthesisArtifact, k: number) => (
                        <div key={k} className={`synthesis-artifact artifact-${art.type}`}>
                          <div className="artifact-header">
                            <span className="artifact-type">{art.type.replace(/_/g, " ")}</span>
                            <span className="artifact-title">{art.title}</span>
                          </div>
                          <div className="artifact-content">
                            <ReactMarkdown>{art.content}</ReactMarkdown>
                          </div>
                          {art.sources.length > 0 && (
                            <div className="artifact-sources">
                              {art.sources.map((src: string, s: number) => (
                                <a key={s} href={src} target="_blank" rel="noopener noreferrer" className="artifact-source">
                                  {new URL(src).hostname}
                                </a>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  {msg.synthesis.full_output && (
                    <div className="synthesis-full-output">
                      <button
                        className="full-output-toggle"
                        onClick={() => setShowFullOutput(!showFullOutput)}
                      >
                        {showFullOutput ? "Hide full output" : "View full output"}
                      </button>
                      {showFullOutput && (
                        <div className="full-output-content">
                          <ReactMarkdown>{msg.synthesis.full_output}</ReactMarkdown>
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
            {msg.actions && msg.actions.length > 0 && (
              <div className="chat-actions">
                {msg.actions.map((action, j) => (
                  <button
                    key={j}
                    className="chat-action-card"
                    onClick={() => handleActionClick(action.action_text)}
                    disabled={busy}
                  >
                    <span className="chat-action-label">{action.label}</span>
                    {action.description && (
                      <span className="chat-action-desc">{action.description}</span>
                    )}
                  </button>
                ))}
                <p className="chat-actions-hint">or type your own message below</p>
              </div>
            )}
          </div>
        ))}
        {activityLog.length > 0 && (
          <div className="activity-log">
            <div className="activity-log-header">
              <span className="activity-pulse" />
              Agent working
            </div>
            <div className="activity-log-entries">
              {activityLog.map((entry, i) => (
                <div key={i} className={`activity-entry ${entry.type}`}>
                  {entry.type === "tool" ? (
                    <span className="activity-tool">{entry.detail}</span>
                  ) : (
                    <span className="activity-text">{entry.text?.slice(0, 120)}{(entry.text?.length ?? 0) > 120 ? "..." : ""}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-area">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            isRecording ? "Listening..." :
            busy ? (isRunning ? "Agent is working..." : "Thinking...") :
            "Tell me what you need..."
          }
          disabled={busy}
          rows={1}
        />
        <button
          className={`mic-btn${isAudioMode ? " active" : ""}${isRecording ? " recording" : ""}${isPlaying ? " playing" : ""}`}
          onClick={handleMicClick}
          title={isRecording ? "Stop recording" : isPlaying ? "Stop playback" : "Voice input"}
        >
          {isRecording ? "⏹" : isPlaying ? "⏸" : "🎤"}
        </button>
        <button onClick={handleSend} disabled={busy || !input.trim()}>
          Send
        </button>
      </div>
    </div>
  );
}
