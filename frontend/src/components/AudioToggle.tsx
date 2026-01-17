interface AudioToggleProps {
  isAudioMode: boolean
  onToggle: () => void
}

export default function AudioToggle({ isAudioMode, onToggle }: AudioToggleProps) {
  return (
    <button
      className={`audio-mode-toggle ${isAudioMode ? 'active' : ''}`}
      onClick={onToggle}
      aria-label={isAudioMode ? 'Switch to text mode' : 'Switch to audio mode'}
    >
      {isAudioMode ? 'Text' : 'Audio'}
    </button>
  )
}
