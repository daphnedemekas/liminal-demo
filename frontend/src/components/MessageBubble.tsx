import { useEffect, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'

interface MessageBubbleProps {
  role: 'user' | 'assistant'
  content: string
  audioUrl?: string
  isAudioMode?: boolean
  onAudioPlay?: () => void
}

// Strip leading/trailing quotes from AI messages (LLMs sometimes wrap responses in quotes)
const stripQuotes = (text: string): string => {
  const trimmed = text.trim()
  if ((trimmed.startsWith('"') && trimmed.endsWith('"')) ||
      (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
    return trimmed.slice(1, -1)
  }
  return text
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

  // Strip quotes from assistant messages
  const displayContent = useMemo(() => {
    if (role === 'assistant') {
      return stripQuotes(content)
    }
    return content
  }, [role, content])

  return (
    <div className={`message-bubble ${role}`}>
      <div className="message-content">
        <ReactMarkdown>{displayContent}</ReactMarkdown>
      </div>
    </div>
  )
}
