import { useEffect } from 'react'
import ReactMarkdown from 'react-markdown'

interface MessageBubbleProps {
  role: 'user' | 'assistant'
  content: string
  audioUrl?: string
  isAudioMode?: boolean
  onAudioPlay?: () => void
}

export default function MessageBubble({
  role,
  content,
  audioUrl,
  isAudioMode,
  onAudioPlay,
}: MessageBubbleProps) {
  // Auto-play audio if in audio mode
  useEffect(() => {
    if (isAudioMode && audioUrl && role === 'assistant' && onAudioPlay) {
      onAudioPlay()
    }
  }, [isAudioMode, audioUrl, role, onAudioPlay])

  return (
    <div className={`message-bubble ${role}`}>
      <div className="message-content">
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
    </div>
  )
}
