import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../services/api";
import type { ChatAction, DiscoveryDomainState } from "../services/api";
import { ContextUpload } from "./ContextUpload";

// Smart truncation: cut at word boundary, add ellipsis
function smartTruncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  const truncated = text.slice(0, maxLength - 3);
  const lastSpace = truncated.lastIndexOf(' ');
  return (lastSpace > maxLength * 0.6 ? truncated.slice(0, lastSpace) : truncated) + '...';
}

interface Message {
  role: string;
  content: string;
  actions?: ChatAction[];
}

// Module-level cache: persists across mount/unmount so returning to a domain is instant
const domainMessageCache = new Map<string, Message[]>();
const domainInputCache = new Map<string, string>();

interface Props {
  userId: string;
  domain: DiscoveryDomainState;
  onProposalsReceived?: (proposals: import("../services/api").DiscoveryProposal[]) => void;
}

export function DomainChat({ userId, domain, onProposalsReceived }: Props) {
  const [messages, setMessages] = useState<Message[]>(() => domainMessageCache.get(domain.domain) || []);
  const [input, setInput] = useState(() => domainInputCache.get(domain.domain) || "");
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Keep caches in sync
  useEffect(() => {
    if (messages.length > 0) {
      domainMessageCache.set(domain.domain, messages);
    }
  }, [messages, domain.domain]);

  useEffect(() => {
    domainInputCache.set(domain.domain, input);
  }, [input, domain.domain]);

  // Load existing conversation or activate domain
  useEffect(() => {
    let cancelled = false;

    // Load from cache instantly (avoids loading flash), then refresh from DB
    const cached = domainMessageCache.get(domain.domain);
    setMessages(cached || []);
    setInput(domainInputCache.get(domain.domain) || "");
    setInitialized(cached ? true : false);

    const init = async () => {
      // Fetch fresh state to get latest conversation (props may be stale)
      let conversation = domain.conversation;
      try {
        const state = await api.getDiscoveryState(userId);
        const fresh = state.domains.find((d) => d.domain === domain.domain);
        if (fresh?.conversation && fresh.conversation.length > 0) {
          conversation = fresh.conversation;
        }
      } catch {
        // fall through to prop data
      }

      if (cancelled) return;

      if (conversation && conversation.length > 0) {
        setMessages(conversation.map((m) => ({
          role: m.role,
          content: m.content,
          actions: [],
        })));
      } else {
        // Activate domain to get opening message
        try {
          const result = await api.activateDomain(userId, domain.domain);
          if (cancelled) return;
          if (result.message) {
            setMessages([{
              role: "assistant",
              content: result.message,
              actions: result.actions || [],
            }]);
          }
        } catch (err) {
          console.error("Failed to activate domain:", err);
        }
      }
      if (!cancelled) setInitialized(true);
    };
    init();
    return () => { cancelled = true; };
  }, [domain.domain, userId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = useCallback(async (text?: string) => {
    const msg = text || input.trim();
    if (!msg || loading) return;
    setInput("");
    setLoading(true);

    try {
      // Normal user message — display it
      setMessages((prev) => [...prev, { role: "user", content: msg }]);

      await api.sendDiscoveryResponseSSE(
        userId,
        msg,
        domain.domain,
        (status) => {
          setStatusMessage(status);
        },
        (result) => {
          setStatusMessage(null);
          // If proposals came back, send them to the panel instead of rendering inline
          if (result.proposed_projects?.length && onProposalsReceived) {
            onProposalsReceived(result.proposed_projects);
            setMessages((prev) => [
              ...prev,
              { role: "assistant", content: result.message, actions: [] },
            ]);
          } else {
            setMessages((prev) => [
              ...prev,
              { role: "assistant", content: result.message, actions: result.actions || [] },
            ]);
          }
          setLoading(false);
        },
        (err) => {
          setStatusMessage(null);
          console.error("Failed to send:", err);
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: "Something went wrong. Try again?" },
          ]);
          setLoading(false);
        },
      );
      return; // loading is cleared in callbacks
    } catch (err) {
      setStatusMessage(null);
      console.error("Failed to send:", err);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Something went wrong. Try again?" },
      ]);
    }
    setLoading(false);
  }, [input, loading, userId, domain.domain, onProposalsReceived]);

  const handleAction = (action: ChatAction) => {
    handleSend(action.action_text ?? "");
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
        <h3>{domain.label}</h3>
        {loading && <span className="running-indicator">{statusMessage || "Thinking…"}</span>}
      </div>

      <div className="chat-messages">
        {!initialized && (
          <div className="empty-chat">
            <p className="hint">Loading...</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i}>
            <div className={`message ${msg.role}`}>
              <div className="message-content">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
              </div>
            </div>
            {msg.actions && msg.actions.length > 0 && (() => {
              // Filter out project accept/skip actions — those are handled by the side panel now
              const nonProjectActions = msg.actions.filter((a: ChatAction) => {
                const at = a.action_text ?? "";
                return !at.startsWith("accept_project:") && at !== "accept_all" && at !== "skip_domain";
              });
              return nonProjectActions.length > 0 ? (
                <div className="chat-actions">
                  {nonProjectActions.map((action, j) => (
                    <button
                      key={j}
                      className="chat-action-card"
                      onClick={() => handleAction(action)}
                      disabled={loading}
                      title={`${action.label}\n${action.description || ''}`}
                    >
                      <span className="chat-action-label">{smartTruncate(action.label, 40)}</span>
                      {action.description && (
                        <span className="chat-action-desc">{smartTruncate(action.description, 100)}</span>
                      )}
                    </button>
                  ))}
                </div>
              ) : null;
            })()}
          </div>
        ))}
        {loading && (
          <div className="message assistant">
            <div className="message-content"><em>{statusMessage || "Thinking…"}</em></div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <ContextUpload
        userId={userId}
        onContextAdded={(title) => {
          setMessages((prev) => [...prev, { role: "system", content: `Context added: ${title}` }]);
        }}
      />
      <div className="chat-input-area">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={loading ? (statusMessage || "Thinking…") : "Type your response..."}
          disabled={loading}
          rows={1}
        />
        <button onClick={() => handleSend()} disabled={loading || !input.trim()}>
          Send
        </button>
      </div>
    </div>
  );
}
