import { useEffect, useRef, useState } from "react";

export interface StreamEvent {
  type: string;
  event_type?: string;
  content?: Record<string, unknown>;
  status?: string;
  result_summary?: string;
  error?: string;
}

export function useRunStream(runId: string | null) {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [status, setStatus] = useState<string>("idle");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!runId) return;

    const wsBase = import.meta.env.VITE_WS_URL || "ws://localhost:8000";
    const ws = new WebSocket(`${wsBase}/ws/run/${runId}`);
    wsRef.current = ws;

    ws.onopen = () => setStatus("connected");

    ws.onmessage = (e) => {
      try {
        const data: StreamEvent = JSON.parse(e.data);
        setEvents((prev) => [...prev, data]);
        if (data.type === "status") {
          setStatus(data.status || "unknown");
        }
      } catch {
        // ignore malformed messages
      }
    };

    ws.onerror = () => setStatus("error");
    ws.onclose = () => setStatus((s) => (s === "done" ? s : "disconnected"));

    return () => {
      ws.close();
      wsRef.current = null;
      setStatus("idle");
      setEvents([]);
    };
  }, [runId]);

  return { events, status };
}
