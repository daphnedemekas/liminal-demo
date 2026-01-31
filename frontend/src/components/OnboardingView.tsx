import { useState, useEffect } from "react";
import { api } from "../services/api";
import type { OnboardingQuestion, OnboardingSuggestion } from "../services/api";

interface Props {
  userId: string;
  userName: string;
  onComplete: () => void;
}

type Phase = "quick_context" | "deeper_qa" | "suggestions";

interface ContextOption {
  id: string;
  label: string;
  icon: string;
}

const ICON_MAP: Record<string, string> = {
  briefcase: "\u{1F4BC}",
  code: "\u{1F4BB}",
  book: "\u{1F4DA}",
  search: "\u{1F50D}",
  home: "\u{1F3E0}",
  compass: "\u{1F9ED}",
};

export function OnboardingView({ userId, userName, onComplete }: Props) {
  const [phase, setPhase] = useState<Phase>("quick_context");
  const [options, setOptions] = useState<ContextOption[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [currentQuestion, setCurrentQuestion] = useState<OnboardingQuestion | null>(null);
  const [questionNumber, setQuestionNumber] = useState(0);
  const [answer, setAnswer] = useState("");
  const [suggestions, setSuggestions] = useState<OnboardingSuggestion[]>([]);
  const [selectedSuggestions, setSelectedSuggestions] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.getOnboardingOptions().then(setOptions);
  }, []);

  const toggleOption = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const fetchNextQuestion = async () => {
    const { question } = await api.getNextQuestion(userId);
    setCurrentQuestion(question);
    setQuestionNumber((n) => n + 1);
  };

  const handleContextSubmit = async () => {
    if (selected.size === 0) return;
    setLoading(true);
    await api.submitQuickContext(userId, [...selected]);
    await fetchNextQuestion();
    setPhase("deeper_qa");
    setLoading(false);
  };

  const handleAnswerSubmit = async () => {
    if (!answer.trim()) return;
    setLoading(true);
    const result = await api.submitOnboardingAnswer(userId, answer.trim());
    setAnswer("");

    if (result.ready_for_suggestions) {
      // Enough info gathered — get suggestions
      const { suggestions: s } = await api.getOnboardingSuggestions(userId);
      setSuggestions(s);
      setSelectedSuggestions(new Set(s.map((_, i) => i)));
      setPhase("suggestions");
    } else {
      // Generate the next adaptive question
      await fetchNextQuestion();
    }
    setLoading(false);
  };

  const toggleSuggestion = (idx: number) => {
    setSelectedSuggestions((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const handleAccept = async () => {
    setLoading(true);
    await api.acceptSuggestions(userId, [...selectedSuggestions]);
    onComplete();
  };

  const handleSkip = async () => {
    setLoading(true);
    await api.skipOnboarding(userId);
    onComplete();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleAnswerSubmit();
    }
  };

  return (
    <div className="onboarding-view">
      <div className="onboarding-container">
        {phase === "quick_context" && (
          <>
            <div className="onboarding-header">
              <h1>Hi {userName}!</h1>
              <p>What brings you to Liminal?</p>
              <p className="onboarding-hint">Select all that apply</p>
            </div>

            <div className="context-grid">
              {options.map((opt) => (
                <button
                  key={opt.id}
                  className={`context-option ${selected.has(opt.id) ? "selected" : ""}`}
                  onClick={() => toggleOption(opt.id)}
                >
                  <span className="context-icon">{ICON_MAP[opt.icon] || ""}</span>
                  <span className="context-label">{opt.label}</span>
                </button>
              ))}
            </div>

            <div className="onboarding-actions">
              <button
                className="onboarding-primary"
                onClick={handleContextSubmit}
                disabled={selected.size === 0 || loading}
              >
                {loading ? "..." : "Continue"}
              </button>
              <button className="onboarding-skip" onClick={handleSkip} disabled={loading}>
                Skip for now
              </button>
            </div>
          </>
        )}

        {phase === "deeper_qa" && currentQuestion && (
          <>
            <div className="onboarding-header">
              <p className="onboarding-step">Question {questionNumber}</p>
              <h2>{currentQuestion.question}</h2>
              <p className="onboarding-hint">{currentQuestion.hint}</p>
            </div>

            <div className="onboarding-input-area">
              <textarea
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type your answer..."
                rows={3}
                autoFocus
              />
            </div>

            <div className="onboarding-actions">
              <button
                className="onboarding-primary"
                onClick={handleAnswerSubmit}
                disabled={!answer.trim() || loading}
              >
                {loading ? "Thinking..." : "Continue"}
              </button>
              <button className="onboarding-skip" onClick={handleSkip} disabled={loading}>
                Skip to dashboard
              </button>
            </div>
          </>
        )}

        {phase === "suggestions" && (
          <>
            <div className="onboarding-header">
              <h2>Here's what I can help with</h2>
              <p>Based on what you told me, I'd suggest starting with these:</p>
            </div>

            <div className="suggestions-list">
              {suggestions.map((s, i) => (
                <div
                  key={i}
                  className={`suggestion-card ${selectedSuggestions.has(i) ? "selected" : ""}`}
                  onClick={() => toggleSuggestion(i)}
                >
                  <div className="suggestion-check">
                    {selectedSuggestions.has(i) ? "\u2713" : ""}
                  </div>
                  <div className="suggestion-body">
                    <h3>{s.name}</h3>
                    <p>{s.description}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="onboarding-actions">
              <button
                className="onboarding-primary"
                onClick={handleAccept}
                disabled={loading}
              >
                {loading
                  ? "..."
                  : selectedSuggestions.size > 0
                    ? `Start ${selectedSuggestions.size} project${selectedSuggestions.size > 1 ? "s" : ""}`
                    : "Go to dashboard"}
              </button>
              <button className="onboarding-skip" onClick={handleSkip} disabled={loading}>
                Skip all
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
