import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../services/api";
import type { Project, ChatAction, SynthesisEvent, MessageBlock } from "../services/api";
import { BlockRenderer } from "./blocks/BlockRenderer";
import { useRunStream } from "../hooks/useRunStream";
import { useAudio } from "../hooks/useAudio";
import { ContextUpload } from "./ContextUpload";

// Smart truncation: cut at word boundary, add ellipsis
function smartTruncate(text: string | undefined | null, maxLength: number): string {
  if (!text) return "";
  if (text.length <= maxLength) return text;
  const truncated = text.slice(0, maxLength - 3);
  const lastSpace = truncated.lastIndexOf(' ');
  return (lastSpace > maxLength * 0.6 ? truncated.slice(0, lastSpace) : truncated) + '...';
}

const DOMAIN_LABELS: Record<string, string> = {
  work: "Work & Career",
  learning: "Learning & Growth",
  health: "Health & Wellness",
  creative: "Creative & Projects",
  money: "Money & Finances",
  mind: "Mind & Wellbeing",
};

function actionLabel(action: ChatAction): string {
  if (action.label) return action.label;
  const at = action.action_text ?? "";
  if (at.startsWith("navigate_domain:")) {
    const domain = at.split(":")[1];
    return `Go to ${DOMAIN_LABELS[domain] || domain}`;
  }
  if (at.startsWith("navigate_project:")) return "Go to project";
  if (at.startsWith("create_project:")) return "Create project";
  return at;
}

interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  actions?: ChatAction[];
  blocks?: MessageBlock[];
  phase?: string;
  timestamp?: string;
  synthesis?: SynthesisEvent;
  nav_context?: string;
}

interface Props {
  project: Project;
  userId: string;
  onProjectRenamed?: () => void;
  onRunComplete?: () => void;
  onNavigateDomain?: (domain: string, context?: string) => void;
  onNavigateProject?: (projectId: number) => void;
  onMessageReceived?: () => void;
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

// Module-level caches: persist across mount/unmount so returning to a project is instant
const messageCache = new Map<number, Message[]>();
const inputCache = new Map<number, string>();

export function ChatPanel({ project, userId, onProjectRenamed, onRunComplete, onNavigateDomain, onNavigateProject, onMessageReceived }: Props) {
  const [messages, setMessages] = useState<Message[]>(() => messageCache.get(project.id) || []);
  const [input, setInput] = useState(() => inputCache.get(project.id) || "");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isChatting, setIsChatting] = useState(false);
  const [activityLog, setActivityLog] = useState<ActivityEntry[]>([]);
  const [researchingTopic, setResearchingTopic] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [logsCollapsed, setLogsCollapsed] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const userScrolledUp = useRef(false);
  const { events, synthesis } = useRunStream(activeRunId);
  const {
    isAudioMode, isRecording, isPlaying, transcript,
    toggleAudioMode, startRecording, stopRecording, playTTS, stopAudio,
  } = useAudio();

  const [blockSelections, setBlockSelections] = useState<Record<string, string[]>>({});
  const [blockSubmitted, setBlockSubmitted] = useState<Set<string>>(new Set());

  const currentProjectId = useRef(project.id);
  const abortRef = useRef<AbortController | null>(null);
  const pendingResultRef = useRef<string | null>(null);
  currentProjectId.current = project.id;

  const sendChat = useCallback(async (text: string, silent = false) => {
    if (isChatting || isRunning || !text) return;

    if (!silent) setMessages((prev) => [...prev, { role: "user", content: text }]);
    setIsChatting(true);

    // Abort any in-flight request and track this one
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const expectedProjectId = project.id;

    try {
      await api.sendChatSSE(
        project.id,
        text,
        (topic) => {
          if (currentProjectId.current !== expectedProjectId) return;
          setResearchingTopic(topic);
          setActivityLog([]); // Clear any previous activity
        },
        (res) => {
          if (currentProjectId.current !== expectedProjectId) return;
          setResearchingTopic(null);
          setStatusMessage(null);
          setActivityLog([]); // Clear research activity when done
          if (res.message) {
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last?.role === "assistant" && last.content === res.message) {
                return prev;
              }
              return [
                ...prev,
                { role: "assistant", content: res.message, actions: res.actions, blocks: res.blocks, phase: res.phase, nav_context: res.nav_context },
              ];
            });
            if (isAudioMode) {
              playTTS(res.message);
            }
          }
          if (res.run_id) {
            setIsRunning(true);
            setActiveRunId(res.run_id);
          }
          setIsChatting(false);
          onMessageReceived?.();
          // Auto-continue: backend signals the next phase should run without user input
          if (res.auto_continue) {
            setTimeout(() => {
              if (currentProjectId.current === expectedProjectId) {
                sendChat("continue", true);
              }
            }, 1500);
          }
        },
        (err) => {
          if (currentProjectId.current !== expectedProjectId) return;
          setResearchingTopic(null);
          setStatusMessage(null);
          setActivityLog([]);
          setMessages((prev) => [
            ...prev,
            { role: "system", content: `Error: ${err.message}` },
          ]);
          setIsChatting(false);
        },
        (status) => {
          if (currentProjectId.current !== expectedProjectId) return;
          setStatusMessage(status);
        },
        controller.signal,
        (tool, input) => {
          if (currentProjectId.current !== expectedProjectId) return;
          const detail = formatToolActivity(tool, input);
          setActivityLog((prev) => [...prev, { type: "tool", tool, detail, timestamp: Date.now() }]);
        },
      );
    } catch (err) {
      if ((err as Error).name === "AbortError") return; // navigated away
      if (currentProjectId.current !== expectedProjectId) return;
      setResearchingTopic(null);
      setStatusMessage(null);
      setMessages((prev) => [
        ...prev,
        { role: "system", content: `Error: ${(err as Error).message}` },
      ]);
      setIsChatting(false);
    }
  }, [project.id, isChatting, isRunning]);

  // Keep caches in sync whenever messages or input update
  useEffect(() => {
    if (messages.length > 0) {
      messageCache.set(project.id, messages);
    }
  }, [messages, project.id]);

  useEffect(() => {
    inputCache.set(project.id, input);
  }, [input, project.id]);

  // Initialize project: reset state, load history, then greet or auto-kickoff
  useEffect(() => {
    // DON'T abort in-flight SSE — let it complete so the backend saves the
    // response to the DB. The currentProjectId guards in all callbacks
    // prevent cross-contamination of state between projects.
    abortRef.current = null;

    // Load cached messages and input for instant display (avoids loading flash)
    const cached = messageCache.get(project.id);
    setMessages(cached || []);
    setInput(inputCache.get(project.id) || "");
    setActiveRunId(null);
    setIsRunning(false);
    setIsChatting(false);
    setActivityLog([]);
    setResearchingTopic(null);
    setStatusMessage(null);

    // Guard against React Strict Mode double-firing this effect
    let cancelled = false;

    const controller = new AbortController();
    abortRef.current = controller;
    const expectedId = project.id;

    const isSuggestedNew = project.suggested_by_system && project.run_count === 0 && project.domain !== "home";

    const init = async () => {
      if (cancelled) return;
      // Load history and check for active runs in parallel
      let hasHistory = false;
      try {
        const [history, activeRunResult] = await Promise.all([
          api.getMessages(project.id),
          api.getActiveRun(project.id),
        ]);
        if (controller.signal.aborted || cancelled) return;

        if (history.length > 0) {
          hasHistory = true;
          setMessages(history.map((m) => ({
            role: m.role as Message["role"],
            content: m.content,
            actions: m.actions,
            blocks: m.blocks,
            phase: m.phase,
            timestamp: m.created_at,
          })));
        }

        // Reconnect to active run if one exists
        if (activeRunResult.active_run) {
          setIsRunning(true);
          setActiveRunId(activeRunResult.active_run.run_id);
          setStatusMessage(`Resuming: ${activeRunResult.active_run.goal.slice(0, 50)}...`);
          return; // WebSocket will handle updates
        }

        if (hasHistory) return; // History loaded, no active run, done
      } catch {
        if (controller.signal.aborted) return;
        // fall through
      }

      // No history and no active run — either auto-kickoff or greeting
      if (cancelled) return;
      if (isSuggestedNew) {
        setIsChatting(true);

        const goal =
          `You are working on the project "${project.name}". ` +
          `Context: ${project.description} ` +
          `Research the landscape: what existing tools, services, and approaches already address this? ` +
          `For each, note what it does, pricing, and how well it fits my specific need. ` +
          `End with a clear recommendation: either "I suggest we set you up with X because..." ` +
          `or "Nothing quite fits — here's the gap, I could build something custom." ` +
          `Be opinionated. Do NOT build anything yet — just research and recommend.`;

        try {
          await api.sendChatSSE(
            project.id,
            goal,
            (topic) => { if (currentProjectId.current === expectedId) { setResearchingTopic(topic); setActivityLog([]); } },
            (res) => {
              if (currentProjectId.current !== expectedId) return;
              setResearchingTopic(null);
              setStatusMessage(null);
              setActivityLog([]);
              if (res.message) {
                setMessages((prev) => [...prev, { role: "assistant", content: res.message, actions: res.actions, blocks: res.blocks, phase: res.phase, nav_context: res.nav_context }]);
              }
              setIsChatting(false);
              onMessageReceived?.();
            },
            (err) => {
              if (currentProjectId.current !== expectedId) return;
              setResearchingTopic(null);
              setStatusMessage(null);
              setActivityLog([]);
              setMessages((prev) => [...prev, { role: "system", content: `Error: ${err}` }]);
              setIsChatting(false);
            },
            (status) => { if (currentProjectId.current === expectedId) setStatusMessage(status); },
            controller.signal,
            (tool, input) => {
              if (currentProjectId.current !== expectedId) return;
              const detail = formatToolActivity(tool, input);
              setActivityLog((prev) => [...prev, { type: "tool", tool, detail, timestamp: Date.now() }]);
            },
          );
        } catch {
          if (currentProjectId.current === expectedId) setIsChatting(false);
        }
      } else {
        // Normal project — request a greeting
        if (controller.signal.aborted) return;
        setIsChatting(true);
        try {
          await api.sendChatSSE(
            project.id,
            undefined,
            (topic) => { if (currentProjectId.current === expectedId) { setResearchingTopic(topic); setActivityLog([]); } },
            (res) => {
              if (currentProjectId.current !== expectedId) return;
              setResearchingTopic(null);
              setStatusMessage(null);
              setActivityLog([]);
              if (res.message) {
                setMessages((prev) => {
                  const last = prev[prev.length - 1];
                  if (last?.role === "assistant" && last.content === res.message) return prev;
                  return [...prev, { role: "assistant", content: res.message, actions: res.actions, blocks: res.blocks, phase: res.phase, nav_context: res.nav_context }];
                });
                if (isAudioMode) playTTS(res.message);
              }
              if (res.run_id) {
                setIsRunning(true);
                setActiveRunId(res.run_id);
              }
              setIsChatting(false);
              onMessageReceived?.();
            },
            (err) => {
              if (currentProjectId.current !== expectedId) return;
              setResearchingTopic(null);
              setStatusMessage(null);
              setActivityLog([]);
              setMessages((prev) => [...prev, { role: "system", content: `Error: ${err.message}` }]);
              setIsChatting(false);
            },
            (status) => { if (currentProjectId.current === expectedId) setStatusMessage(status); },
            controller.signal,
            (tool, input) => {
              if (currentProjectId.current !== expectedId) return;
              const detail = formatToolActivity(tool, input);
              setActivityLog((prev) => [...prev, { type: "tool", tool, detail, timestamp: Date.now() }]);
            },
          );
        } catch {
          if (currentProjectId.current === expectedId) setIsChatting(false);
        }
      }
    };
    init();

    // Don't abort on cleanup — let SSE complete in background so backend
    // work (LLM calls, research, agent runs) isn't interrupted.
    // The currentProjectId guards in all callbacks prevent cross-contamination.
    // Abort only happens at the TOP of this effect when re-initializing.
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
      // Store result for fallback if synthesis fails, but don't add to messages yet.
      // Synthesis will add the summary; if it fails, done handler adds fallback.
      const text = (lastEvent.content as Record<string, string>)?.text;
      pendingResultRef.current = text || null;
      // Don't clear activityLog here — run isn't done yet
    }

    if (lastEvent.type === "status" && lastEvent.status === "done") {
      setActivityLog([]);
      setIsRunning(false);
      setActiveRunId(null);
      // Wait briefly for synthesis to arrive before adding fallback
      setTimeout(() => {
        if (pendingResultRef.current) {
          const fallbackText = pendingResultRef.current.slice(0, 500) +
            (pendingResultRef.current.length > 500 ? "..." : "");
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: `Task completed. ${fallbackText}` },
          ]);
          pendingResultRef.current = null;
        }
        onRunComplete?.();
      }, 3000);
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

    // Clear pending result so the done-handler timeout won't add a duplicate fallback
    pendingResultRef.current = null;

    // Only add if not already present (prevents duplicate on reload from DB)
    setMessages((prev) => {
      const alreadyExists = prev.some(
        (m) => m.role === "assistant" && m.content === synthesis.summary
      );
      if (alreadyExists) return prev;
      return [
        ...prev,
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
    onRunComplete?.();
  }, [synthesis, onRunComplete]);

  // Track whether user has scrolled up - check position before any state change
  const checkIfNearBottom = () => {
    const container = messagesContainerRef.current;
    if (!container) return true; // Default to auto-scroll if no container
    const { scrollTop, scrollHeight, clientHeight } = container;
    return scrollHeight - scrollTop - clientHeight <= 100;
  };

  // Update scroll position tracking on scroll events
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    const handleScroll = () => {
      userScrolledUp.current = !checkIfNearBottom();
    };
    container.addEventListener("scroll", handleScroll);
    return () => container.removeEventListener("scroll", handleScroll);
  }, []);

  // Auto-scroll only when user is already at the bottom
  // Use a small delay to let DOM update first
  useEffect(() => {
    const shouldScroll = !userScrolledUp.current;
    if (shouldScroll) {
      requestAnimationFrame(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
      });
    }
  }, [messages, activityLog, researchingTopic]);

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

  const handleBlockSelect = (blockId: string, values: string[]) => {
    setBlockSelections((prev) => ({ ...prev, [blockId]: values }));
  };

  const handleBlockSubmit = (blockId: string, text: string) => {
    setBlockSubmitted((prev) => new Set(prev).add(blockId));

    // If this is a CTA action (build/adjust), include current selections from other blocks
    if (text === "build" || text === "adjust") {
      const selections = Object.entries(blockSelections)
        .filter(([, values]) => values.length > 0)
        .map(([id, values]) => `${id}:${values.join(",")}`)
        .join("|");
      const fullMessage = selections ? `${text}|${selections}` : text;
      sendChat(fullMessage, true);
    } else {
      sendChat(text, true);
    }
  };

  const handleActionClick = (actionText: string) => {
    if (isRunning || isChatting) return;

    // Intercept navigation actions — pass context from home chat
    if (actionText.startsWith("navigate_domain:")) {
      const domain = actionText.split(":")[1];
      const msgWithAction = [...messages].reverse().find(m =>
        m.actions?.some((a: { action_text?: string }) => a.action_text === actionText)
      );
      onNavigateDomain?.(domain, msgWithAction?.nav_context);
      return;
    }
    if (actionText.startsWith("navigate_project:")) {
      const id = parseInt(actionText.split(":")[1], 10);
      if (!isNaN(id)) {
        onNavigateProject?.(id);
        return;
      }
    }

    sendChat(actionText, true);
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
          {isChatting && !isRunning && <span className="running-indicator">{statusMessage || "Thinking…"}</span>}
          <button
            className={`audio-mode-toggle${isAudioMode ? " active" : ""}`}
            onClick={toggleAudioMode}
            title={isAudioMode ? "Disable auto-speak" : "Enable auto-speak"}
          >
            {isAudioMode ? "Voice On" : "Voice Off"}
          </button>
        </div>
      </div>

      <div className="chat-messages" ref={messagesContainerRef}>
        {messages.length === 0 && busy && (
          <div className="chat-loading-indicator">
            <span className="loading-dot" />
            <span>{statusMessage || "Getting started…"}</span>
          </div>
        )}
        {messages.length === 0 && !busy && (
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
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                )}
              </div>
              {msg.synthesis?.artifacts && msg.synthesis.artifacts.length > 0 && (
                <div className="synthesis-workspace-hint">
                  {msg.synthesis.artifacts.length} item{msg.synthesis.artifacts.length > 1 ? "s" : ""} added to workspace →
                </div>
              )}
            </div>
            {msg.blocks && msg.blocks.length > 0 && (
              <div className="message-blocks">
                {msg.blocks.map((block) => (
                  <BlockRenderer
                    key={block.id}
                    block={block}
                    selection={blockSelections[block.id] || []}
                    submitted={blockSubmitted.has(block.id)}
                    submittedText={undefined}
                    disabled={busy}
                    onSelect={(values) => handleBlockSelect(block.id, values)}
                    onSubmit={(text) => handleBlockSubmit(block.id, text)}
                  />
                ))}
              </div>
            )}
            {msg.actions && msg.actions.length > 0 && (
              <div className="chat-actions">
                {msg.actions.filter((a) => a.action_text || a.label).map((action, j) => (
                  <button
                    key={j}
                    className="chat-action-card"
                    onClick={() => handleActionClick(action.action_text ?? "")}
                    disabled={busy}
                    title={`${action.label}\n${action.description || ''}`}
                  >
                    <span className="chat-action-label">{smartTruncate(actionLabel(action), 40)}</span>
                    {action.description && (
                      <span className="chat-action-desc">{smartTruncate(action.description, 100)}</span>
                    )}
                  </button>
                ))}
                <p className="chat-actions-hint">or type your own message below</p>
              </div>
            )}
          </div>
        ))}
        {(activityLog.length > 0 || researchingTopic) && (
          <div className={`activity-log ${logsCollapsed ? "collapsed" : ""}`}>
            <div className="activity-log-header" onClick={() => setLogsCollapsed((c) => !c)}>
              <span className="activity-pulse" />
              <span className="activity-log-title">
                {researchingTopic ? `Researching: ${researchingTopic}` : "Agent working"}
              </span>
              <span className="activity-log-toggle">{logsCollapsed ? "▸ Show logs" : "▾ Hide logs"}</span>
            </div>
            {!logsCollapsed && (
              <div className="activity-log-entries">
                {activityLog.map((entry, i) => (
                  <div key={i} className={`activity-entry ${entry.type}`}>
                    {entry.type === "tool" ? (
                      <span className="activity-tool">{entry.detail}</span>
                    ) : (
                      <span className="activity-text">{entry.text?.slice(0, 200)}{(entry.text?.length ?? 0) > 200 ? "..." : ""}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <ContextUpload
        userId={userId}
        projectId={project.id}
        onContextAdded={(title) => {
          setMessages((prev) => [...prev, { role: "system", content: `Context added: ${title}` }]);
        }}
      />
      <div className="chat-input-area">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            isRecording ? "Listening..." :
            busy ? (isRunning ? "Agent is working..." : (statusMessage || "Thinking…")) :
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
          {isRecording ? "Stop" : isPlaying ? "Pause" : "Mic"}
        </button>
        <button onClick={handleSend} disabled={busy || !input.trim()}>
          Send
        </button>
      </div>
    </div>
  );
}
