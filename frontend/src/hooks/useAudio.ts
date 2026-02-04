import { useState, useCallback, useRef, useEffect } from "react";

const BASE = import.meta.env.VITE_API_URL || "";

interface UseAudioReturn {
  isAudioMode: boolean;
  isRecording: boolean;
  isPlaying: boolean;
  transcript: string;
  toggleAudioMode: () => void;
  startRecording: () => void;
  stopRecording: () => void;
  playTTS: (text: string) => Promise<void>;
  stopAudio: () => void;
}

export function useAudio(): UseAudioReturn {
  const [isAudioMode, setIsAudioMode] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [transcript, setTranscript] = useState("");

  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    return () => {
      recognitionRef.current?.stop();
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.src = "";
      }
    };
  }, []);

  const toggleAudioMode = useCallback(() => {
    setIsAudioMode((prev) => !prev);
  }, []);

  const startRecording = useCallback(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Speech recognition not supported in this browser.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      const results = Array.from(event.results);
      const text = results.map((r) => r[0].transcript).join("");
      setTranscript(text);
    };

    recognition.onerror = () => {
      setIsRecording(false);
    };

    recognition.onend = () => {
      setIsRecording(false);
    };

    recognitionRef.current = recognition;
    setTranscript("");
    setIsRecording(true);
    recognition.start();
  }, []);

  const stopRecording = useCallback(() => {
    recognitionRef.current?.stop();
    setIsRecording(false);
  }, []);

  const playTTS = useCallback(async (text: string) => {
    try {
      const res = await fetch(`${BASE}/api/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) return;

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;

      audio.onended = () => {
        setIsPlaying(false);
        URL.revokeObjectURL(url);
        audioRef.current = null;
      };
      audio.onerror = () => {
        setIsPlaying(false);
        URL.revokeObjectURL(url);
      };

      setIsPlaying(true);
      await audio.play();
    } catch {
      setIsPlaying(false);
    }
  }, []);

  const stopAudio = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = "";
      audioRef.current = null;
    }
    setIsPlaying(false);
  }, []);

  return {
    isAudioMode,
    isRecording,
    isPlaying,
    transcript,
    toggleAudioMode,
    startRecording,
    stopRecording,
    playTTS,
    stopAudio,
  };
}
