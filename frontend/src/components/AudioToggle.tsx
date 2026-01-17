interface AudioToggleProps {
  isAudioMode: boolean
  onToggle: () => void
}

export default function AudioToggle({ isAudioMode, onToggle }: AudioToggleProps) {
  return (
    <button
      className="audio-toggle"
      onClick={onToggle}
      aria-label={isAudioMode ? 'Switch to text' : 'Switch to audio'}
    >
      {isAudioMode ? '📝' : '🎤'}
    </button>
  )
}
