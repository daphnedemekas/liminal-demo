import { useEffect, useMemo, useRef } from 'react'
import ReactMarkdown from 'react-markdown'

interface MessageBubbleProps {
  role: 'user' | 'assistant'
  content: string
  audioUrl?: string
  isAudioMode?: boolean
  isUserRecording?: boolean  // Don't auto-play while user is recording
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
  isUserRecording,
  onAudioPlay,
}: MessageBubbleProps) {
  // Track if we've already played audio for this message to prevent loops
  const hasPlayedAudioRef = useRef(false)
  // Track the previous audio URL to detect NEW audio arriving
  const prevAudioUrlRef = useRef<string | undefined>(undefined)
  
  // Auto-play audio ONLY when:
  // 1. Audio mode is on
  // 2. This is a NEW audio URL (just arrived), not an existing one
  // 3. User is not recording
  // 4. Haven't already played it
  useEffect(() => {
    // Don't auto-play while user is actively recording
    if (isUserRecording) {
      return
    }
    
    // Check if this is a NEW audio URL arriving (not one that existed before)
    const isNewAudio = audioUrl && audioUrl !== prevAudioUrlRef.current
    prevAudioUrlRef.current = audioUrl
    
    // Only auto-play if:
    // - Audio mode is on
    // - This is an assistant message
    // - Audio URL is new (just arrived)
    // - We haven't played it yet
    // - Audio mode was ALREADY on before this audio arrived (or was on when component mounted)
    if (isAudioMode && audioUrl && role === 'assistant' && isNewAudio && !hasPlayedAudioRef.current && onAudioPlay) {
      // Small delay to ensure we're not interrupting anything
      console.log('[MessageBubble] New audio arrived, playing...')
      hasPlayedAudioRef.current = true
      onAudioPlay()
    }
  }, [isAudioMode, isUserRecording, audioUrl, role, onAudioPlay])

  // Strip quotes and JSON markers from assistant messages
  const displayContent = useMemo(() => {
    if (role === 'assistant') {
      let cleaned = stripQuotes(content)
      // Remove any JSON marker strings that might have slipped through
      if (cleaned.includes('__TASK_CURRICULUM_PROPOSED__:')) {
        // Extract just the text before the marker, or use a default message
        const parts = cleaned.split('__TASK_CURRICULUM_PROPOSED__:')
        cleaned = parts[0].trim() || "Here's the learning path I've designed for you."
      }
      return cleaned
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
