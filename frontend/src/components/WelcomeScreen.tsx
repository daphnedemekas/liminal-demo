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
            Imagine having scientists and engineers working around the clock to
            help you lead your best life—freeing up your time, accelerating your
            learning, surfacing opportunities you'd never find alone.
          </p>
          <p className="welcome-highlight">That's what we build for you.</p>
          <p>
            Tell us what matters—your health, finances, creative work,
            relationships, or something you can't quite name yet—and we'll show
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
