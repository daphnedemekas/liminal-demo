interface Props {
  onContinue: () => void;
}

export function WelcomeScreen({ onContinue }: Props) {
  return (
    <div className="login-screen">
      <div className="welcome-card">
        <h1>Welcome to Envisage</h1>
        <p className="welcome-tagline">Your personal AI infrastructure team.</p>
        <div className="welcome-body">
          <p>
             
          </p> 
          <p className="welcome-highlight">We build agents for human agency.</p>
          <p>
            Tell us what matters to you, and we'll show
            you exactly how today's AI can help. Not generic tools. Solutions
            designed to fit your life.
          </p>
          <p className="welcome-closing">
            You stay in control. We handle the complexity.
          </p>
        </div>
        <button className="welcome-continue" onClick={onContinue}>
          Continue
        </button>
      </div>
    </div>
  );
}
