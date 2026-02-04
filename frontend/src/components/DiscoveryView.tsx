import { useState, useEffect } from "react";
import { api } from "../services/api";
import type { IntegrationStatusResponse } from "../services/api";

interface Props {
  userId: string;
  userName: string;
  onComplete: () => void;
}

type Screen =
  | "welcome"
  | "how_it_works"
  | "domain_select"
  | "not_sure"
  | "recommendation"
  | "permissions"
  | "what_to_expect";

const DOMAINS = [
  { id: "work", label: "Work & Career", description: "Career growth, productivity, professional goals", icon: "\u{1F4BC}" },
  { id: "learning", label: "Learning & Growth", description: "Skills, courses, knowledge building", icon: "\u{1F4DA}" },
  { id: "health", label: "Health & Wellness", description: "Fitness, nutrition, sleep, habits", icon: "\u{1F49A}" },
  { id: "creative", label: "Creative & Projects", description: "Hobbies, side projects, creative pursuits", icon: "\u{1F3A8}" },
  { id: "money", label: "Money & Finances", description: "Budgeting, saving, investing, expenses", icon: "\u{1F4B0}" },
  { id: "mind", label: "Mind & Wellbeing", description: "Stress, mindfulness, mental clarity", icon: "\u{1F9E0}" },
];

const HOW_IT_WORKS_STEPS = [
  { title: "Talk", description: "Tell me what you're working on, what's frustrating you, or what you want to change." },
  { title: "Surface", description: "I'll research what exists, break down the problem, and show you real options." },
  { title: "Decide", description: "You pick what to build. I show you the tradeoffs and what I'd recommend." },
  { title: "Compound", description: "As I learn more about you, the help gets more specific and the results build on each other." },
];

// Diagnostic questions for the "not sure" path
const NOT_SURE_QUESTIONS = [
  {
    id: "pain_point",
    prompt: "What feels like the biggest drag on your day-to-day right now?",
    options: [
      { value: "time", label: "Not enough time", description: "Too many things, not enough hours" },
      { value: "direction", label: "Lack of direction", description: "Not sure what to focus on" },
      { value: "energy", label: "Low energy or motivation", description: "Know what to do, can't get going" },
      { value: "overwhelm", label: "Information overload", description: "Too many options, can't decide" },
    ],
  },
  {
    id: "aspiration",
    prompt: "If you could wave a magic wand, what would change first?",
    options: [
      { value: "career", label: "My career trajectory", description: "Growth, income, impact" },
      { value: "skills", label: "My skills or knowledge", description: "Learning something new or going deeper" },
      { value: "health_habits", label: "My health or habits", description: "Physical or mental wellbeing" },
      { value: "projects", label: "A project I care about", description: "Something creative or personal" },
      { value: "money_clarity", label: "Financial clarity", description: "Knowing where I stand and what to do" },
    ],
  },
  {
    id: "timeframe",
    prompt: "Are you looking for a quick win or a longer-term change?",
    options: [
      { value: "quick", label: "Quick win", description: "Something I can see results from this week" },
      { value: "medium", label: "Next few months", description: "Willing to invest time for bigger payoff" },
      { value: "long", label: "Long-term transformation", description: "Ready to build something lasting" },
    ],
  },
];

// Simple mapping from diagnostic answers to recommended domain
function recommendDomain(answers: Record<string, string>): { domain: string; reason: string } {
  const { pain_point, aspiration } = answers;

  // Aspiration-first matching
  if (aspiration === "career") return { domain: "work", reason: "Your career goals are the clearest starting point — I can research opportunities, optimize your workflow, and help you make strategic moves." };
  if (aspiration === "skills") return { domain: "learning", reason: "You want to grow your skills — I can find the best resources, build a learning plan, and keep you on track." };
  if (aspiration === "health_habits") return { domain: "health", reason: "Health and habits compound over time — I can help you build systems that stick." };
  if (aspiration === "projects") return { domain: "creative", reason: "You've got a project you care about — I can handle the tedious parts so you can focus on the creative work." };
  if (aspiration === "money_clarity") return { domain: "money", reason: "Financial clarity removes a huge source of background stress — I can help you see where you stand and what to do next." };

  // Fallback to pain-point matching
  if (pain_point === "energy") return { domain: "mind", reason: "When energy is the bottleneck, starting with your mental wellbeing has the biggest ripple effect on everything else." };
  if (pain_point === "time") return { domain: "work", reason: "Time pressure usually originates from work — let's start there and free up bandwidth for everything else." };
  if (pain_point === "direction") return { domain: "learning", reason: "When you're not sure where to focus, structured learning and exploration can clarify what matters most." };
  if (pain_point === "overwhelm") return { domain: "mind", reason: "When everything feels like too much, starting with mental clarity helps you make better decisions everywhere else." };

  return { domain: "work", reason: "Work is usually a good starting point — it touches everything else and tends to have the most immediate impact." };
}

export function DiscoveryView({ userId, userName, onComplete }: Props) {
  const [screen, setScreen] = useState<Screen>("welcome");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [notSureStep, setNotSureStep] = useState(0);
  const [notSureAnswers, setNotSureAnswers] = useState<Record<string, string>>({});
  const [recommendation, setRecommendation] = useState<{ domain: string; reason: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [integrations, setIntegrations] = useState<IntegrationStatusResponse | null>(null);
  const [connectingGoogle, setConnectingGoogle] = useState(false);

  const firstName = userName.split(" ")[0];

  // Fetch integration status when permissions screen is shown
  useEffect(() => {
    if (screen === "permissions") {
      api.getIntegrationStatus(userId).then(setIntegrations).catch(() => {});
    }
  }, [screen, userId]);

  const toggleDomain = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleFinish = async (domains: string[]) => {
    setLoading(true);
    try {
      if (domains.length > 0) {
        await api.selectDomains(userId, domains);
      }
      await api.completeDiscovery(userId, {
        selected_domains: domains,
        diagnostic_answers: Object.keys(notSureAnswers).length > 0 ? notSureAnswers : undefined,
      });
      onComplete();
    } catch (err) {
      console.error("Failed to complete onboarding:", err);
      setLoading(false);
    }
  };

  const handleNotSureAnswer = (value: string) => {
    const question = NOT_SURE_QUESTIONS[notSureStep];
    const updated = { ...notSureAnswers, [question.id]: value };
    setNotSureAnswers(updated);

    if (notSureStep < NOT_SURE_QUESTIONS.length - 1) {
      setNotSureStep(notSureStep + 1);
    } else {
      // All questions answered — generate recommendation
      const rec = recommendDomain(updated);
      setRecommendation(rec);
      setScreen("recommendation");
    }
  };

  // ── Screen renderers ──────────────────────────────────────────────

  if (screen === "welcome") {
    return (
      <div className="onboarding-view">
        <div className="onboarding-container onboarding-centered">
          <div className="onboarding-header">
            <h1>Hi {firstName}</h1>
            <p className="onboarding-subtitle">
              I'm Envisage — an AI that works alongside you to get things done, not just answer questions.
            </p>
          </div>
          <div className="onboarding-actions">
            <button className="onboarding-primary" onClick={() => setScreen("how_it_works")}>
              Let's get started
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (screen === "how_it_works") {
    return (
      <div className="onboarding-view">
        <div className="onboarding-container">
          <div className="onboarding-header">
            <h2>How this works</h2>
            <p>Four steps, repeated across anything you throw at me.</p>
          </div>

          <div className="how-it-works-steps">
            {HOW_IT_WORKS_STEPS.map((step, i) => (
              <div key={step.title} className="how-step">
                <div className="how-step-number">{i + 1}</div>
                <div className="how-step-content">
                  <div className="how-step-title">{step.title}</div>
                  <div className="how-step-desc">{step.description}</div>
                </div>
              </div>
            ))}
          </div>

          <div className="onboarding-actions">
            <button className="onboarding-primary" onClick={() => setScreen("domain_select")}>
              Continue
            </button>
            <button className="onboarding-back" onClick={() => setScreen("welcome")}>
              Back
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (screen === "domain_select") {
    return (
      <div className="onboarding-view">
        <div className="onboarding-container">
          <div className="onboarding-header">
            <h2>Where should we start?</h2>
            <p>Pick one or more domains to focus on first. You can always add more later.</p>
          </div>

          <div className="context-grid">
            {DOMAINS.map((d) => (
              <button
                key={d.id}
                className={`context-option ${selected.has(d.id) ? "selected" : ""}`}
                onClick={() => toggleDomain(d.id)}
              >
                <span className="context-icon">{d.icon}</span>
                <span className="context-label">{d.label}</span>
              </button>
            ))}
          </div>

          <div className="onboarding-actions">
            <button
              className="onboarding-primary"
              onClick={() => setScreen("permissions")}
              disabled={selected.size === 0}
            >
              Continue
            </button>
            <button
              className="onboarding-text-btn"
              onClick={() => {
                setNotSureStep(0);
                setNotSureAnswers({});
                setScreen("not_sure");
              }}
            >
              Not sure — help me figure it out
            </button>
          </div>

          <div className="onboarding-nav-back">
            <button className="onboarding-back" onClick={() => setScreen("how_it_works")}>
              Back
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (screen === "not_sure") {
    const question = NOT_SURE_QUESTIONS[notSureStep];
    return (
      <div className="onboarding-view">
        <div className="onboarding-container onboarding-centered">
          <div className="onboarding-header">
            <p className="onboarding-step-label">Question {notSureStep + 1} of {NOT_SURE_QUESTIONS.length}</p>
            <h2>{question.prompt}</h2>
          </div>

          <div className="not-sure-options">
            {question.options.map((opt) => (
              <button
                key={opt.value}
                className="not-sure-option"
                onClick={() => handleNotSureAnswer(opt.value)}
              >
                <div className="not-sure-option-label">{opt.label}</div>
                <div className="not-sure-option-desc">{opt.description}</div>
              </button>
            ))}
          </div>

          <div className="onboarding-nav-back">
            <button
              className="onboarding-back"
              onClick={() => {
                if (notSureStep > 0) setNotSureStep(notSureStep - 1);
                else setScreen("domain_select");
              }}
            >
              Back
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (screen === "recommendation") {
    const rec = recommendation!;
    const domain = DOMAINS.find((d) => d.id === rec.domain)!;
    return (
      <div className="onboarding-view">
        <div className="onboarding-container onboarding-centered">
          <div className="onboarding-header">
            <h2>I'd start here</h2>
          </div>

          <div className="recommendation-card">
            <span className="recommendation-icon">{domain.icon}</span>
            <div className="recommendation-label">{domain.label}</div>
            <p className="recommendation-reason">{rec.reason}</p>
          </div>

          <div className="onboarding-actions">
            <button
              className="onboarding-primary"
              onClick={() => {
                setSelected(new Set([rec.domain]));
                setScreen("permissions");
              }}
            >
              Start with {domain.label}
            </button>
            <button
              className="onboarding-text-btn"
              onClick={() => setScreen("domain_select")}
            >
              Let me pick myself
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (screen === "permissions") {
    const gcal = integrations?.google_calendar;
    const gcalConnected = gcal?.connected ?? false;
    const gcalAvailable = gcal?.available ?? false;

    const handleConnectGoogle = async () => {
      setConnectingGoogle(true);
      try {
        const { auth_url } = await api.getGoogleAuthUrl(userId);
        // Open OAuth in a popup
        const popup = window.open(auth_url, "google_oauth", "width=500,height=600");
        // Poll for popup close (callback redirects back to app)
        const interval = setInterval(() => {
          if (popup?.closed) {
            clearInterval(interval);
            setConnectingGoogle(false);
            // Refresh integration status
            api.getIntegrationStatus(userId).then(setIntegrations).catch(() => {});
          }
        }, 500);
      } catch {
        setConnectingGoogle(false);
      }
    };

    return (
      <div className="onboarding-view">
        <div className="onboarding-container">
          <div className="onboarding-header">
            <h2>Connect your world</h2>
            <p>The more context I have, the more useful I can be. You can always add these later.</p>
          </div>

          <div className="permissions-list">
            <div className="permission-item">
              <div className="permission-info">
                <div className="permission-label">Google Calendar</div>
                <div className="permission-desc">See your schedule to give time-aware advice</div>
              </div>
              {gcalConnected ? (
                <span className="permission-connected">Connected</span>
              ) : (
                <button
                  className="permission-btn permission-btn-active"
                  onClick={handleConnectGoogle}
                  disabled={!gcalAvailable || connectingGoogle}
                >
                  {connectingGoogle ? "Connecting..." : gcalAvailable ? "Connect" : "Not configured"}
                </button>
              )}
            </div>
            <div className="permission-item">
              <div className="permission-info">
                <div className="permission-label">Oura / Health</div>
                <div className="permission-desc">Track sleep, activity, and readiness</div>
              </div>
              <button className="permission-btn" disabled>Coming soon</button>
            </div>
            <div className="permission-item">
              <div className="permission-info">
                <div className="permission-label">Notion</div>
                <div className="permission-desc">Access your notes and documents</div>
              </div>
              <button className="permission-btn" disabled>Coming soon</button>
            </div>
          </div>

          <div className="onboarding-actions">
            <button className="onboarding-primary" onClick={() => setScreen("what_to_expect")}>
              Continue
            </button>
            <button className="onboarding-back" onClick={() => setScreen("domain_select")}>
              Back
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (screen === "what_to_expect") {
    return (
      <div className="onboarding-view">
        <div className="onboarding-container onboarding-centered">
          <div className="onboarding-header">
            <h2>What to expect</h2>
          </div>

          <div className="expect-list">
            <div className="expect-item">
              <div className="expect-title">I'll ask before I act</div>
              <div className="expect-desc">You'll always see what I'm about to do and approve it first.</div>
            </div>
            <div className="expect-item">
              <div className="expect-title">I remember what matters</div>
              <div className="expect-desc">Every conversation teaches me about you. I get more useful over time.</div>
            </div>
            <div className="expect-item">
              <div className="expect-title">I research before I recommend</div>
              <div className="expect-desc">I don't guess — I look up real tools, real prices, and real options.</div>
            </div>
            <div className="expect-item">
              <div className="expect-title">You stay in control</div>
              <div className="expect-desc">Change direction, pause, or start over anytime. Nothing is permanent.</div>
            </div>
          </div>

          <div className="onboarding-actions">
            <button
              className="onboarding-primary"
              onClick={() => handleFinish([...selected])}
              disabled={loading}
            >
              {loading ? "Setting up..." : "Let's go"}
            </button>
            <button className="onboarding-back" onClick={() => setScreen("permissions")}>
              Back
            </button>
          </div>
        </div>
      </div>
    );
  }

  return null;
}
