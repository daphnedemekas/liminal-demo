import { useState, useEffect, useRef, useCallback } from 'react'
import { useWebSocket, Message } from '../hooks/useWebSocket'
import { useAudio } from '../hooks/useAudio'
import { useSpeechRecognition } from '../hooks/useSpeechRecognition'
import { api } from '../services/api'
import MessageBubble from './MessageBubble'
import ProfilePanel from './ProfilePanel'
import FeedPanel from './FeedPanel'
import AudioToggle from './AudioToggle'
import BreathingCircle from './BreathingCircle'
import { ModelConfig } from './ModelSelector'

interface TeachingCandidate {
  id: number
  topic: string
  focus_question: string
  identified_gap: string
  readiness_score: number
  goalConversationHistory?: Array<{ role: string; content: string }>
}

interface GoalChatProps {
  goalId: number  // Database goal ID for resuming
  goal: string
  userId: string  // User ID for persistence
  modelConfig: ModelConfig
  onboardingInfo: string
  onTeachingCandidateAccepted: (candidate: TeachingCandidate) => void
  onCurriculumAccepted?: (tasks: TeachingCandidate[]) => void  // When curriculum of multiple tasks is accepted
}

export default function GoalChat({
  goalId,
  goal,
  userId,
  modelConfig,
  onboardingInfo,
  onTeachingCandidateAccepted,
  onCurriculumAccepted
}: GoalChatProps) {
  const [inputText, setInputText] = useState('')
  const [actualSessionId, setActualSessionId] = useState<string | null>(null)
  const [initialized, setInitialized] = useState(false)
  const [isResumed, setIsResumed] = useState(false)
  const [profileSummary, setProfileSummary] = useState<string | undefined>(undefined)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const initRef = useRef(false)

  const { messages, sendMessage, sendCommand, isConnected, status, addMessage, setMessages } = useWebSocket(actualSessionId || '', 'discovery')
  const { isAudioMode, isPlaying, toggleAudioMode, playAudio } = useAudio()
  const {
    isListening,
    transcript,
    startListening,
    stopListening,
    isSupported: isSpeechSupported,
    resetTranscript,
  } = useSpeechRecognition()

  // handleSend must be defined before any useEffect that depends on it
  const handleSend = useCallback((text?: string) => {
    const messageText = text || inputText.trim()
    if (!messageText || !isConnected) return

    sendMessage(messageText)
    setInputText('')
  }, [inputText, isConnected, sendMessage])

  // Initialize or resume goal-specific session
  useEffect(() => {
    if (initRef.current) return
    initRef.current = true

    console.log('[GoalChat] Initializing goal session for:', goal, 'goalId:', goalId)

    // Start/resume discovery session with user_id and goal_id
    api.startDiscoverySession(modelConfig, goal, userId, goalId).then((response) => {
      console.log('[GoalChat] Goal session response:', {
        session_id: response.session_id,
        is_resumed: response.is_resumed,
        history_length: response.conversation_history?.length || 0
      })
      
      setActualSessionId(response.session_id)
      setIsResumed(response.is_resumed)
      
      // Load profile summary if available
      if (response.profile_summary) {
        setProfileSummary(response.profile_summary)
      }
      
      // If resuming, load the conversation history
      if (response.is_resumed && response.conversation_history?.length > 0) {
        console.log('[GoalChat] Resuming with', response.conversation_history.length, 'messages')
        // Skip the first user message if it's the onboarding/background info
        // (the AI's first response already incorporates this context)
        let historyToRestore = response.conversation_history
        if (historyToRestore.length > 0 && historyToRestore[0].role === 'user') {
          historyToRestore = historyToRestore.slice(1)
        }
        const restoredMessages: Message[] = historyToRestore.map((msg: any, idx: number) => ({
          id: `restored-${idx}`,
          role: msg.role as 'user' | 'assistant',
          content: msg.content,
        }))
        setMessages(restoredMessages)
      } else if (response.opening_message && response.opening_message.trim()) {
        // New session - add opening message
        addMessage({
          id: crypto.randomUUID(),
          role: 'assistant',
          content: response.opening_message,
        })
      }
      
      setInitialized(true)
    }).catch(err => {
      console.error('[GoalChat] Failed to start goal session:', err)
    })
  }, [goalId, goal, userId, modelConfig, addMessage, setMessages])

  // Send onboarding info once connected
  // For new sessions OR resumed sessions with no history (first time opening goal panel)
  // Use sendCommand to send silently - don't show onboarding in chat UI
  const [onboardingSent, setOnboardingSent] = useState(false)
  useEffect(() => {
    // Send onboarding if:
    // 1. Connected and initialized
    // 2. Not already sent
    // 3. Have onboarding info
    // 4. Either: not resumed, OR resumed but with no messages (first time opening goal panel)
    const needsOnboarding = !isResumed || messages.length === 0
    if (isConnected && initialized && !onboardingSent && onboardingInfo && needsOnboarding) {
      console.log('[GoalChat] Sending onboarding to trigger opening message', { isResumed, messagesLength: messages.length })
      setOnboardingSent(true)
      // Send the user's background context silently (not shown in UI)
      setTimeout(() => {
        sendCommand(onboardingInfo)
      }, 100)
    }
  }, [isConnected, initialized, isResumed, onboardingSent, onboardingInfo, messages.length, sendCommand])

  // Check for create_teaching_panel - notify parent to create new teaching panel
  useEffect(() => {
    const lastMessage = messages[messages.length - 1]
    if (lastMessage?.type === 'create_teaching_panel' && lastMessage.teachingCandidate) {
      console.log('[GoalChat] Creating teaching panel:', lastMessage.teachingCandidate.topic)
      // Pass the goal conversation history along with the candidate
      const conversationHistory = messages
        .filter(m => m.role === 'user' || m.role === 'assistant')
        .map(m => ({ role: m.role, content: m.content }))
      onTeachingCandidateAccepted({
        ...lastMessage.teachingCandidate,
        goalConversationHistory: conversationHistory
      })
    }
  }, [messages, onTeachingCandidateAccepted])

  // Check for task_curriculum_accepted - notify parent to add all tasks
  useEffect(() => {
    const lastMessage = messages[messages.length - 1]
    if (lastMessage?.type === 'task_curriculum_accepted' && lastMessage.tasks) {
      console.log('[GoalChat] Curriculum accepted with tasks:', lastMessage.tasks)
      const conversationHistory = messages
        .filter(m => m.role === 'user' || m.role === 'assistant')
        .map(m => ({ role: m.role, content: m.content }))

      // Add goal conversation history to all tasks
      const tasksWithHistory = lastMessage.tasks.map((task: any) => ({
        ...task,
        goalConversationHistory: conversationHistory
      }))

      if (onCurriculumAccepted) {
        onCurriculumAccepted(tasksWithHistory)
      }
    }
  }, [messages, onCurriculumAccepted])

  // Track if we've played audio for the current last message
  const [lastPlayedMessageId, setLastPlayedMessageId] = useState<string | null>(null)
  // Track when audio finished to add delay before recording
  const [audioEndTime, setAudioEndTime] = useState<number>(0)

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
  useEffect(() => {
    const lastMessage = messages[messages.length - 1]
    if (isAudioMode && lastMessage?.role === 'assistant' && lastMessage?.audio_url && !isPlaying && lastMessage.id !== lastPlayedMessageId) {
      console.log('[Voice] Auto-playing audio for message:', lastMessage.id)
      // Stop any recording before playing
      if (isListening) {
        stopListening()
      }
      setLastPlayedMessageId(lastMessage.id)
      const timer = setTimeout(() => {
        playAudio(lastMessage.audio_url!)
      }, 200)
      return () => clearTimeout(timer)
    }
  }, [messages, isAudioMode, isPlaying, playAudio, lastPlayedMessageId, isListening, stopListening])

  // Stop recording when processing starts
  useEffect(() => {
    if (status && isListening) {
      console.log('[Voice] Stopping recording - processing started')
      stopListening()
    }
  }, [status, isListening, stopListening])

  // Auto-start recording when AI finishes speaking in voice mode
  useEffect(() => {
    const lastMessage = messages[messages.length - 1]
    // Don't auto-start recording if:
    // 1. There's pending audio that hasn't been played yet
    // 2. Audio is currently playing
    // 3. We're processing a response (status is set)
    // 4. No messages yet (waiting for opening)
    // 5. Audio ended too recently (give 1.5s buffer to avoid echo)
    const hasPendingAudio = lastMessage?.role === 'assistant' && lastMessage?.audio_url && lastMessage.id !== lastPlayedMessageId
    const isProcessing = !!status
    const hasNoMessages = messages.length === 0
    const timeSinceAudioEnd = Date.now() - audioEndTime
    const audioJustEnded = audioEndTime > 0 && timeSinceAudioEnd < 1500
    
    if (isAudioMode && !isPlaying && !isListening && isSpeechSupported && !hasPendingAudio && !isProcessing && !hasNoMessages && !audioJustEnded) {
      const timer = setTimeout(() => {
        if (!isPlaying) {
          console.log('[Voice] Starting recording after audio finished')
          startListening()
        }
      }, 500)
      return () => clearTimeout(timer)
    }
    
    // If audio just ended, schedule a check for when the delay is over
    if (isAudioMode && !isPlaying && !isListening && isSpeechSupported && !hasPendingAudio && !isProcessing && !hasNoMessages && audioJustEnded) {
      const remainingDelay = 1500 - timeSinceAudioEnd + 100
      const timer = setTimeout(() => {
        if (!isPlaying) {
          console.log('[Voice] Starting recording after audio delay')
          startListening()
        }
      }, remainingDelay)
      return () => clearTimeout(timer)
    }
  }, [isPlaying, isAudioMode, isListening, isSpeechSupported, startListening, messages, lastPlayedMessageId, status, audioEndTime])

  // Handle spacebar to stop recording and send
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't intercept if user is typing in an input/textarea
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

  // Check for teaching candidate proposed (legacy single-candidate flow)
  const lastTeachingProposedIndex = messages.findLastIndex(m => m.type === 'teaching_proposed')
  const lastTeachingPanelIndex = messages.findLastIndex(m => m.type === 'create_teaching_panel' || m.type === 'teaching_accepted')
  const hasPendingTeaching = lastTeachingProposedIndex > lastTeachingPanelIndex && lastTeachingProposedIndex >= 0
  const pendingTeachingProposal = hasPendingTeaching ? messages[lastTeachingProposedIndex] : null

  // Check for task curriculum proposed (new batch proposal flow)
  const lastCurriculumProposedIndex = messages.findLastIndex(m => m.type === 'task_curriculum_proposed')
  const lastCurriculumAcceptedIndex = messages.findLastIndex(m => m.type === 'task_curriculum_accepted')
  const hasPendingCurriculum = lastCurriculumProposedIndex > lastCurriculumAcceptedIndex && lastCurriculumProposedIndex >= 0
  const pendingCurriculumProposal = hasPendingCurriculum ? messages[lastCurriculumProposedIndex] : null

  // Handle teaching candidate accept/reject (legacy)
  const handleAcceptTeaching = () => {
    if (isConnected) {
      sendCommand('__ACCEPT_TEACHING__')
    }
  }

  const handleRejectTeaching = () => {
    if (isConnected) {
      sendCommand('__REJECT_TEACHING__')
    }
  }

  // Handle task curriculum accept/modify (new)
  const handleAcceptCurriculum = () => {
    if (isConnected) {
      sendCommand('__ACCEPT_CURRICULUM__')
    }
  }

  const handleModifyCurriculum = () => {
    // Focus the input field for user to type modification
    const input = document.querySelector('.goal-chat-input input') as HTMLInputElement
    if (input) {
      input.focus()
      input.placeholder = 'What would you like to change about this curriculum?'
    }
  }

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="discovery-with-feed">
      {/* Feed Panel */}
      <FeedPanel
        userId={userId}
        contextType="goal"
        goalId={goalId}
        goalText={goal}
        userBackground={onboardingInfo}
      />

      <div className="goal-chat-layout">
        {/* Chat Area */}
        <div className="goal-chat" style={{ position: 'relative' }}>
          {/* Voice Mode Overlay - covers the chat panel */}
          <BreathingCircle 
            isVisible={isAudioMode} 
            isAISpeaking={isPlaying}
            isUserRecording={isListening && !status}
            isProcessing={!!status || messages.length === 0}
            onTap={() => {
              if (status || messages.length === 0) {
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
            statusText={isListening && !status ? transcript : undefined}
          />

          {/* Goal Header */}
          <div className="goal-chat-header">
          <div className="goal-chat-title">
            <span className="goal-icon"></span>
            <h2>{goal}</h2>
          </div>
          <div className="goal-chat-status">
            <AudioToggle isAudioMode={isAudioMode} onToggle={toggleAudioMode} />
            {isResumed && <span className="resumed-badge">Resumed</span>}
            {status ? (
              <span className="status-indicator-small">
                <span className="status-dot"></span>
                {status}
              </span>
            ) : isConnected ? (
              <span className="connected-indicator">Connected</span>
            ) : (
              <span className="connecting-indicator">Connecting...</span>
            )}
          </div>
        </div>

        {/* Messages */}
        <div className="goal-chat-messages" style={{ position: 'relative' }}>
          {messages.map((msg, index) => (
            <div key={msg.id}>
              <MessageBubble
                role={msg.role}
                content={msg.content}
                audioUrl={msg.audio_url}
                isAudioMode={isAudioMode}
                onAudioPlay={() => msg.audio_url && playAudio(msg.audio_url)}
              />
              {/* Show teaching candidate confirmation buttons (legacy single-candidate) */}
              {msg.type === 'teaching_proposed' && 
               msg.teachingCandidate && 
               index === lastTeachingProposedIndex && 
               hasPendingTeaching && (
                <div className="teaching-confirmation">
                  <div className="teaching-candidate-preview">
                    <h4>Suggested Starting Point</h4>
                    <p className="teaching-topic">{msg.teachingCandidate.topic}</p>
                    {msg.teachingCandidate.focus_question && (
                      <p className="teaching-question">"{msg.teachingCandidate.focus_question}"</p>
                    )}
                  </div>
                  <div className="teaching-confirmation-buttons">
                    <button 
                      className="teaching-accept-btn"
                      onClick={handleAcceptTeaching}
                      disabled={!isConnected}
                    >
                      Let's start here
                    </button>
                    <button 
                      className="teaching-reject-btn"
                      onClick={handleRejectTeaching}
                      disabled={!isConnected}
                    >
                      Not quite — explore more
                    </button>
                  </div>
                </div>
              )}

              {/* Show task curriculum Accept/Modify buttons (new batch proposal) */}
              {msg.type === 'task_curriculum_proposed' && 
               index === lastCurriculumProposedIndex && 
               hasPendingCurriculum && (
                <div className="curriculum-confirmation">
                  <div className="curriculum-confirmation-buttons">
                    <button 
                      className="curriculum-accept-btn"
                      onClick={handleAcceptCurriculum}
                      disabled={!isConnected}
                    >
                      Accept — Let's start
                    </button>
                    <button 
                      className="curriculum-modify-btn"
                      onClick={handleModifyCurriculum}
                      disabled={!isConnected}
                    >
                      Modify
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}

          {status && (
            <div className="status-indicator">
              <div className="status-spinner"></div>
              <span>{status}</span>
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
                placeholder="Continue exploring this goal..."
                disabled={!isConnected}
              />
              <button
                className="send-button"
                onClick={() => handleSend()}
                disabled={!inputText.trim() || !isConnected}
              >
                Send
              </button>
            </div>
          </div>
        )}
      </div>

        {/* Profile Panel */}
        <ProfilePanel 
          sessionId={actualSessionId} 
          isConnected={isConnected} 
          initialSummary={profileSummary}
        />
      </div>
    </div>
  )
}
