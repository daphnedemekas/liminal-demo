import { useEffect, useRef, useState } from "react";
import type { SynthesisEvent } from "../services/api";

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
  const [synthesis, setSynthesis] = useState<SynthesisEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!runId) return;

    setSynthesis(null);
    const wsBase = import.meta.env.VITE_WS_URL || "ws://localhost:8000";
    const ws = new WebSocket(`${wsBase}/ws/run/${runId}`);
    wsRef.current = ws;

    ws.onopen = () => setStatus("connected");

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === "synthesis") {
          setSynthesis(data as SynthesisEvent);
        } else {
          setEvents((prev) => [...prev, data as StreamEvent]);
          if (data.type === "status") {
            setStatus(data.status || "unknown");
          }
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
      setSynthesis(null);
    };
  }, [runId]);

  return { events, status, synthesis };
}
