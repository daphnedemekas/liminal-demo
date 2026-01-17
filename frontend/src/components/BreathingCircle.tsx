interface BreathingCircleProps {
  isVisible: boolean
  isAISpeaking: boolean
  isUserRecording: boolean
  isProcessing?: boolean
  onTap?: () => void
  onExit?: () => void
  statusText?: string
}

export default function BreathingCircle({ 
  isVisible, 
  isAISpeaking, 
  isUserRecording,
  isProcessing = false,
  onTap,
  onExit,
  statusText
}: BreathingCircleProps) {
  if (!isVisible) return null

  // Determine the current state
  let stateClass = 'idle'
  let stateLabel = 'TAP TO SPEAK'
  let stateIcon = '🎤'
  
  if (isProcessing) {
    stateClass = 'processing'
    stateLabel = 'THINKING...'
    stateIcon = '💭'
  } else if (isAISpeaking) {
    stateClass = 'ai-speaking'
    stateLabel = 'AI SPEAKING'
    stateIcon = '🔊'
  } else if (isUserRecording) {
    stateClass = 'user-recording'
    stateLabel = 'LISTENING • TAP TO SEND'
    stateIcon = '🎙️'
  }

  return (
    <div className="voice-overlay">
      {/* Exit button */}
      {onExit && (
        <button 
          className="voice-exit-btn"
          onClick={onExit}
          aria-label="Exit voice mode"
        >
          ✕ Text Mode
        </button>
      )}

      {/* State indicator at top */}
      <div className="voice-state-indicator">
        <span className="voice-state-icon">{stateIcon}</span>
        <span className="voice-state-label">{stateLabel}</span>
      </div>

      {/* Main voice circle */}
      <div 
        className={`voice-circle ${stateClass}`}
        onClick={onTap}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && onTap?.()}
      >
        <div className="voice-circle-ring ring-1" />
        <div className="voice-circle-ring ring-2" />
        <div className="voice-circle-ring ring-3" />
        <div className="voice-circle-core">
          {isProcessing && (
            <div className="voice-processing-dots">
              <span></span><span></span><span></span>
            </div>
          )}
        </div>
      </div>

      {/* Transcript display when recording */}
      {isUserRecording && statusText && (
        <div className="voice-transcript">
          "{statusText}"
        </div>
      )}

      {/* Hint text */}
      <div className="voice-hint">
        {isUserRecording 
          ? 'Tap circle or press SPACE to send' 
          : isAISpeaking 
            ? 'Wait for AI to finish...'
            : isProcessing
              ? 'Processing your message...'
              : 'Tap the circle to start speaking'}
      </div>
    </div>
  )
}
