import { useState } from 'react'

interface OnboardingScreenProps {
  onComplete: (info: string, goal?: string) => void
}

type OnboardingStep = 'goal-choice' | 'goal-input' | 'goal-background' | 'background-input'

export default function OnboardingScreen({ onComplete }: OnboardingScreenProps) {
  const [step, setStep] = useState<OnboardingStep>('goal-choice')
  const [backgroundInfo, setBackgroundInfo] = useState('')
  const [goal, setGoal] = useState('')

  const handleGoalChoice = (hasGoal: boolean) => {
    if (hasGoal) {
      setStep('goal-input')
    } else {
      setStep('background-input')
    }
  }

  const handleGoalSubmit = () => {
    if (goal.trim()) {
      setStep('goal-background')
    }
  }

  const handleSubmitWithGoal = () => {
    if (backgroundInfo.trim()) {
      onComplete(backgroundInfo.trim(), goal.trim())
    }
  }

  const handleSubmitWithoutGoal = () => {
    if (backgroundInfo.trim()) {
      onComplete(backgroundInfo.trim(), undefined)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent, submitFn: () => void) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submitFn()
    }
  }

  return (
    <div className="onboarding-screen">
      <div className="onboarding-content">
        <h1>Welcome to Liminal Discovery</h1>

        {step === 'goal-choice' && (
          <div className="onboarding-message">
            <p className="onboarding-intro">
              Do you have a specific learning goal in mind?
            </p>
            <p className="onboarding-note">
              For example: "Understand jazz harmony", "Learn vector calculus", "Master chess endgames"
            </p>

            <div className="onboarding-button-group">
              <button
                className="onboarding-choice-button"
                onClick={() => handleGoalChoice(true)}
              >
                Yes, I have a goal
              </button>
              <button
                className="onboarding-choice-button"
                onClick={() => handleGoalChoice(false)}
              >
                No, let's explore
              </button>
            </div>
          </div>
        )}

        {step === 'goal-input' && (
          <div className="onboarding-input-container">
            <div className="onboarding-message">
              <p className="onboarding-prompt">
                What would you like to learn?
              </p>
              <p className="onboarding-note">
                We'll help you find the best first step toward this goal.
              </p>
            </div>

            <input
              type="text"
              className="onboarding-goal-input"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              onKeyPress={(e) => handleKeyPress(e, handleGoalSubmit)}
              placeholder="e.g., Understand jazz harmony, Learn vector calculus, Master chess endgames"
              autoFocus
            />

            <div className="onboarding-button-row">
              <button
                className="onboarding-back-button"
                onClick={() => setStep('goal-choice')}
              >
                Back
              </button>
              <button
                className="onboarding-submit-button"
                onClick={handleGoalSubmit}
                disabled={!goal.trim()}
              >
                Next
              </button>
            </div>
          </div>
        )}

        {step === 'goal-background' && (
          <div className="onboarding-input-container">
            <div className="onboarding-message">
              <p className="onboarding-intro">
                Great! To help find the best first step toward "{goal}", tell me a bit about yourself:
              </p>
              <p className="onboarding-note">
                Just a sentence or two about your background, interests, or why this goal matters to you.
              </p>
            </div>

            <textarea
              className="onboarding-textarea"
              value={backgroundInfo}
              onChange={(e) => setBackgroundInfo(e.target.value)}
              onKeyPress={(e) => handleKeyPress(e, handleSubmitWithGoal)}
              placeholder="e.g., I'm a software engineer interested in Eastern philosophy, or I practice yoga and want to understand the theory behind it..."
              rows={4}
              autoFocus
            />

            <div className="onboarding-button-row">
              <button
                className="onboarding-back-button"
                onClick={() => setStep('goal-input')}
              >
                Back
              </button>
              <button
                className="onboarding-submit-button"
                onClick={handleSubmitWithGoal}
                disabled={!backgroundInfo.trim()}
              >
                Start Discovery Session
              </button>
            </div>
          </div>
        )}

        {step === 'background-input' && (
          <div className="onboarding-input-container">
            <div className="onboarding-message">
              <p className="onboarding-intro">
                Tell me briefly about yourself so I can personalize our conversation:
              </p>

              <ul className="onboarding-questions">
                <li>What do you do for work or study?</li>
                <li>What are some of your hobbies or interests?</li>
                <li>Do you have any particular curiosities right now?</li>
                <li>Do you prefer deep dives into specific topics, or exploring a broad space?</li>
              </ul>

              <p className="onboarding-note">
                (Just share what feels comfortable - this helps me tailor the conversation to you!)
              </p>
            </div>

            <textarea
              className="onboarding-textarea"
              value={backgroundInfo}
              onChange={(e) => setBackgroundInfo(e.target.value)}
              onKeyPress={(e) => handleKeyPress(e, handleSubmitWithoutGoal)}
              placeholder="Type your response here..."
              rows={6}
              autoFocus
            />

            <div className="onboarding-button-row">
              <button
                className="onboarding-back-button"
                onClick={() => setStep('goal-choice')}
              >
                Back
              </button>
              <button
                className="onboarding-submit-button"
                onClick={handleSubmitWithoutGoal}
                disabled={!backgroundInfo.trim()}
              >
                Start Discovery Session
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
