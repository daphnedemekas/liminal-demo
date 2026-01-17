import { useState, useEffect, useRef, useCallback } from 'react'
import { useAudio } from '../hooks/useAudio'
import { useSpeechRecognition } from '../hooks/useSpeechRecognition'
import MessageBubble from './MessageBubble'
import ProfilePanel from './ProfilePanel'
import FeedPanel from './FeedPanel'
import AudioToggle from './AudioToggle'
import BreathingCircle from './BreathingCircle'

interface TeachingCandidate {
  id: number
  topic: string
  focus_question: string
  identified_gap: string
  goalConversationHistory?: Array<{ role: string; content: string }>
  current_model_summary?: string
  stakes_summary?: string
}

interface TeachingChatProps {
  candidate: TeachingCandidate
  goalId: number
  goalText: string
  userId: string
  onboardingInfo: string
  modelConfig?: { interviewer?: string; ranker?: string }
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
}

interface CurriculumProgress {
  current_step: number
  total_steps: number
  completed_steps: number
}

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function TeachingChat({ 
  candidate, 
  goalId, 
  goalText,
  userId,
  onboardingInfo,
  modelConfig
}: TeachingChatProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [inputText, setInputText] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [isResumed, setIsResumed] = useState(false)
  const [curriculumProgress, setCurriculumProgress] = useState<CurriculumProgress | null>(null)
  const [narrativeSummary, setNarrativeSummary] = useState<string>('')
  const [status, setStatus] = useState<string | null>(null)
  
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const initRef = useRef(false)

  const { isAudioMode, isPlaying, toggleAudioMode, playAudio } = useAudio()
  const {
    isListening,
    transcript,
    startListening,
    stopListening,
    isSupported: isSpeechSupported,
    resetTranscript,
  } = useSpeechRecognition()

  // Initialize teaching session
  useEffect(() => {
    if (initRef.current) return
    initRef.current = true

    const initializeTeaching = async () => {
      setIsLoading(true)
      setStatus('Initializing teaching session...')
      
      try {
        const response = await fetch(`${API_URL}/api/teaching/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: userId,
            goal_id: goalId,
            goal_text: goalText,
            teaching_candidate_id: candidate.id,
            topic: candidate.topic,
            identified_gap: candidate.identified_gap,
            focus_question: candidate.focus_question,
            goal_conversation_history: candidate.goalConversationHistory || [],
            user_background: onboardingInfo,
            current_model_summary: candidate.current_model_summary,
            stakes_summary: candidate.stakes_summary,
            llm_config: modelConfig
          })
        })

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }

        const data = await response.json()
        setSessionId(data.session_id)
        setIsResumed(data.is_resumed)
        
        // Restore conversation history if resuming
        if (data.is_resumed && data.conversation_history?.length > 0) {
          const restoredMessages: Message[] = data.conversation_history.map(
            (msg: { role: string; content: string }, idx: number) => ({
              id: `restored-${idx}`,
              role: msg.role as 'user' | 'assistant',
              content: msg.content
            })
          )
          setMessages(restoredMessages)
          console.log(`[TeachingChat] Restored ${restoredMessages.length} messages`)
        } else if (data.opening_message) {
          // New session - add opening message
          setMessages([{
            id: 'opening',
            role: 'assistant',
            content: data.opening_message
          }])
        }

        // Store curriculum plan info if available
        if (data.curriculum_plan) {
          setCurriculumProgress({
            current_step: 0,
            total_steps: data.curriculum_plan.steps?.length || 0,
            completed_steps: data.curriculum_plan.completed_step_ids?.length || 0
          })
        }

        // Connect WebSocket
        connectWebSocket(data.session_id)
        
      } catch (error) {
        console.error('[TeachingChat] Init error:', error)
        setStatus('Failed to initialize. Please refresh.')
        
        // Fallback message
        setMessages([{
          id: 'fallback',
          role: 'assistant',
          content: `Let's explore **${candidate.topic}** together.\n\n${candidate.focus_question}\n\nFeel free to ask questions or tell me what aspect interests you most.`
        }])
      } finally {
        setIsLoading(false)
        setStatus(null)
      }
    }

    initializeTeaching()

    return () => {
      // Cleanup WebSocket on unmount
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [candidate, goalId, goalText, userId, onboardingInfo])

  const connectWebSocket = useCallback((sid: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('[TeachingChat] WebSocket already connected')
      return
    }

    console.log(`[TeachingChat] Connecting WebSocket for session ${sid.slice(0, 8)}...`)
    const ws = new WebSocket(`${WS_URL}/ws/teaching/${sid}`)

    ws.onopen = () => {
      console.log('[TeachingChat] WebSocket connected')
      setIsConnected(true)
    }

    ws.onclose = () => {
      console.log('[TeachingChat] WebSocket disconnected')
      setIsConnected(false)
    }

    ws.onerror = (error) => {
      console.error('[TeachingChat] WebSocket error:', error)
      setIsConnected(false)
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      console.log('[TeachingChat] Received:', data.type)

      switch (data.type) {
        case 'status':
          setStatus(data.status)
          break

        case 'teaching_message':
          setMessages(prev => [...prev, {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: data.content
          }])
          setIsLoading(false)
          setStatus(null)
          
          // Update progress
          if (data.curriculum_progress) {
            setCurriculumProgress(data.curriculum_progress)
          }
          if (data.narrative_summary) {
            setNarrativeSummary(data.narrative_summary)
          }
          break

        case 'teaching_complete':
          setMessages(prev => [...prev, {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: data.content
          }])
          setIsLoading(false)
          setStatus('Teaching complete!')
          // Could show completion UI here
          break

        case 'error':
          console.error('[TeachingChat] Error:', data.message)
          setMessages(prev => [...prev, {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: `⚠️ ${data.message}`
          }])
          setIsLoading(false)
          setStatus(null)
          break

        default:
          console.log('[TeachingChat] Unknown message type:', data.type)
      }
    }

    wsRef.current = ws
  }, [])

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // handleSend must be defined before any useEffect that depends on it
  const handleSend = useCallback((text?: string) => {
    const messageText = text || inputText.trim()
    if (!messageText || isLoading || !isConnected) return

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: messageText
    }

    setMessages(prev => [...prev, userMessage])
    setInputText('')
    setIsLoading(true)
    setStatus('Processing...')

    // Send via WebSocket
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ content: messageText }))
    } else {
      console.error('[TeachingChat] WebSocket not connected')
      setIsLoading(false)
      setStatus('Connection lost. Please refresh.')
    }
  }, [inputText, isLoading, isConnected])

  // Track when audio finished to add delay before recording
  const [audioEndTime, setAudioEndTime] = useState<number>(0)
  const [lastPlayedMessageId, setLastPlayedMessageId] = useState<string | null>(null)

  // Stop recording IMMEDIATELY when audio is about to play
  useEffect(() => {
    if (isPlaying && isListening) {
      console.log('[Voice] Stopping recording - audio playing')
      stopListening()
    }
  }, [isPlaying, isListening, stopListening])

  // Track when audio ends
  useEffect(() => {
    if (!isPlaying && lastPlayedMessageId) {
      setAudioEndTime(Date.now())
    }
  }, [isPlaying, lastPlayedMessageId])

  // Auto-play TTS when AI responds in voice mode (ElevenLabs)
  // Note: TeachingChat doesn't have audio_url yet but this prepares for when it's added
  useEffect(() => {
    const lastMessage = messages[messages.length - 1]
    if (isAudioMode && lastMessage?.role === 'assistant' && (lastMessage as any)?.audio_url && !isPlaying && lastMessage.id !== lastPlayedMessageId) {
      // Stop any recording before playing
      if (isListening) {
        stopListening()
      }
      setLastPlayedMessageId(lastMessage.id)
      playAudio((lastMessage as any).audio_url)
    }
  }, [messages, isAudioMode, isPlaying, playAudio, lastPlayedMessageId, isListening, stopListening])

  // Stop recording when processing starts
  useEffect(() => {
    if (isLoading && isListening) {
      console.log('[Voice] Stopping recording - processing started')
      stopListening()
    }
  }, [isLoading, isListening, stopListening])

  // Auto-start recording when AI finishes speaking in voice mode
  useEffect(() => {
    // Don't auto-start if loading, no messages, or not connected
    // Also add delay after audio ends to avoid echo
    const hasNoMessages = messages.length === 0
    const timeSinceAudioEnd = Date.now() - audioEndTime
    const audioJustEnded = audioEndTime > 0 && timeSinceAudioEnd < 1500
    
    if (isAudioMode && !isPlaying && !isListening && isSpeechSupported && !isLoading && isConnected && !hasNoMessages && !audioJustEnded) {
      const timer = setTimeout(() => {
        if (!isPlaying && !isLoading) {
          console.log('[Voice] Starting recording after audio finished')
          startListening()
        }
      }, 500)
      return () => clearTimeout(timer)
    }
    
    // If audio just ended, schedule a check for when the delay is over
    if (isAudioMode && !isPlaying && !isListening && isSpeechSupported && !isLoading && isConnected && !hasNoMessages && audioJustEnded) {
      const remainingDelay = 1500 - timeSinceAudioEnd + 100
      const timer = setTimeout(() => {
        if (!isPlaying && !isLoading) {
          console.log('[Voice] Starting recording after audio delay')
          startListening()
        }
      }, remainingDelay)
      return () => clearTimeout(timer)
    }
  }, [isPlaying, isAudioMode, isListening, isSpeechSupported, isLoading, isConnected, startListening, messages, audioEndTime])

  // Handle spacebar to stop recording and send
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
        return
      }

      if (e.code === 'Space' && isListening && isAudioMode) {
        e.preventDefault()
        stopListening()

        // Send the transcript after stopping
        if (transcript && transcript.trim()) {
          handleSend(transcript)
          resetTranscript()
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isListening, isAudioMode, stopListening, transcript, handleSend, resetTranscript])

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="discovery-with-feed">
      {/* Feed Panel - Left side */}
      <FeedPanel
        userId={userId}
        contextType="teaching_candidate"
        goalId={goalId}
        goalText={goalText}
        teachingTopic={candidate.topic}
        userBackground={onboardingInfo}
      />

      <div className="goal-chat-layout">
        {/* Chat Area - Center */}
        <div className="goal-chat" style={{ position: 'relative' }}>
          {/* Voice Mode Overlay - covers the chat panel */}
          <BreathingCircle 
            isVisible={isAudioMode} 
            isAISpeaking={isPlaying}
            isUserRecording={isListening && !isLoading}
            isProcessing={isLoading || messages.length === 0}
            onTap={() => {
              if (isLoading || messages.length === 0) {
                // Don't do anything while processing or waiting for opening
                return
              }
              if (isListening) {
                stopListening()
                if (transcript && transcript.trim()) {
                  handleSend(transcript)
                  resetTranscript()
                }
              } else if (!isPlaying) {
                startListening()
              }
            }}
            onExit={toggleAudioMode}
            statusText={isListening && !isLoading ? transcript : undefined}
          />

          {/* Header */}
          <div className="goal-chat-header">
            <div className="goal-chat-title">
              <span className="goal-icon">📚</span>
              <h2>{candidate.topic}</h2>
              {isResumed && <span className="resumed-badge">Resumed</span>}
            </div>
            <div className="goal-chat-status">
              <AudioToggle isAudioMode={isAudioMode} onToggle={toggleAudioMode} />
              
              {/* Curriculum Progress */}
              {curriculumProgress && curriculumProgress.total_steps > 0 && (
                <span className="curriculum-progress">
                  Step {curriculumProgress.current_step + 1}/{curriculumProgress.total_steps}
                  {curriculumProgress.completed_steps > 0 && 
                    ` (${curriculumProgress.completed_steps} done)`}
                </span>
              )}
              
              <span className="goal-context-badge">Goal: {goalText}</span>
              
              {/* Connection status */}
              <span className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
                {isConnected ? '●' : '○'}
              </span>
            </div>
          </div>

          {/* Narrative Summary Banner (when available) */}
          {narrativeSummary && (
            <div className="narrative-summary-banner">
              <strong>Progress:</strong> {narrativeSummary}
            </div>
          )}

          {/* Messages */}
          <div className="goal-chat-messages" style={{ position: 'relative' }}>
            {messages.map((msg) => (
              <MessageBubble
                key={msg.id}
                role={msg.role}
                content={msg.content}
              />
            ))}
            {(isLoading || status) && (
              <div className="status-indicator">
                <div className="status-spinner"></div>
                <span>{status || 'Thinking...'}</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input - hidden in voice mode since overlay handles it */}
          {!isAudioMode && (
            <div className="goal-chat-input">
              <div className="text-input-container">
                <input
                  type="text"
                  className="text-input"
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="Ask a question or share what you're thinking..."
                  disabled={isLoading || !isConnected}
                />
                <button
                  className="send-button"
                  onClick={() => handleSend()}
                  disabled={!inputText.trim() || isLoading || !isConnected}
                >
                  Send
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Profile Panel - Right side (for teaching state) */}
        <ProfilePanel 
          sessionId={sessionId} 
          isConnected={isConnected}
          isTeachingSession={true}
        />
      </div>
    </div>
  )
}
