import { useState, useEffect, useRef } from 'react'
import { useWebSocket } from '../hooks/useWebSocket'
import { useAudio } from '../hooks/useAudio'
import { useSpeechRecognition } from '../hooks/useSpeechRecognition'
import { api } from '../services/api'
import MessageBubble from './MessageBubble'
import AudioToggle from './AudioToggle'
import ProfilePanel from './ProfilePanel'
import FeedPanel from './FeedPanel'
import { ModelConfig } from './ModelSelector'

interface DiscoveryChatProps {
  sessionId: string
  modelConfig: ModelConfig
  onboardingInfo: string
  userGoal?: string
  userId?: string  // For persistent sessions
  onTopicFound: (topic: any) => void
  onGoalAccepted?: (goal: string, sessionId: string) => void
}

export default function DiscoveryChat({ sessionId: _initialSessionId, modelConfig, onboardingInfo, userGoal, userId, onTopicFound, onGoalAccepted }: DiscoveryChatProps) {
  const [inputText, setInputText] = useState('')
  const [actualSessionId, setActualSessionId] = useState<string | null>(null)
  const [onboardingSent, setOnboardingSent] = useState(false)
  const [isResumed, setIsResumed] = useState(false)
  const [profileSummary, setProfileSummary] = useState<string | undefined>(undefined)
  const [queuedOpening, setQueuedOpening] = useState<{ content: string; audio_url?: string } | null>(null)
  const initRef = useRef(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const { messages, sendMessage, sendCommand, isConnected, status, addMessage, setMessages } = useWebSocket(actualSessionId || '', 'discovery')
  const { isAudioMode, toggleAudioMode, playAudio } = useAudio()
  const {
    isListening,
    transcript,
    startListening,
    stopListening,
    isSupported: isSpeechSupported,
  } = useSpeechRecognition()

  // Initialize session and get opening message
  useEffect(() => {
    console.log('[DiscoveryChat] Component mounted, initializing session...')

    // React 18 StrictMode runs effects twice in dev; guard so we don't double-create sessions / duplicate messages.
    if (initRef.current) {
      console.log('[DiscoveryChat] Already initialized, skipping')
      return
    }
    initRef.current = true

    console.log('[DiscoveryChat] Starting discovery session with model config:', modelConfig, 'userId:', userId)

    // Pass userId for persistence (no goal for exploration)
    api.startDiscoverySession(modelConfig, undefined, userId).then((response) => {
      console.log('[DiscoveryChat] Session response:', {
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
        console.log('[DiscoveryChat] Resuming with', response.conversation_history.length, 'messages')
        const restoredMessages = response.conversation_history.map((msg: any, idx: number) => ({
          id: `restored-${idx}`,
          role: msg.role as 'user' | 'assistant',
          content: msg.content,
        }))
        setMessages(restoredMessages)
        setOnboardingSent(true)  // Don't re-send onboarding for resumed sessions
        setQueuedOpening({ content: '', audio_url: undefined })  // No need for opening
        
        // Refresh history after a short delay to catch any in-flight saves
        // (handles race condition when navigating away during long processing)
        setTimeout(async () => {
          try {
            const freshData = await api.startDiscoverySession(modelConfig, undefined, userId)
            if (freshData.conversation_history?.length > response.conversation_history.length) {
              console.log('[DiscoveryChat] Found newer history:', freshData.conversation_history.length, 'messages')
              const freshMessages = freshData.conversation_history.map((msg: any, idx: number) => ({
                id: `restored-fresh-${idx}`,
                role: msg.role as 'user' | 'assistant',
                content: msg.content,
              }))
              setMessages(freshMessages)
            }
          } catch (err) {
            console.error('[DiscoveryChat] Failed to refresh history:', err)
          }
        }, 2000)  // Wait 2 seconds for any pending saves to complete
      } else if (response.opening_message && response.opening_message.trim()) {
        // New session with opening message
        setQueuedOpening({
          content: response.opening_message,
          audio_url: response.audio_url || undefined,
        })
        console.log('[DiscoveryChat] Queued opening message:', response.opening_message.substring(0, 50) + '...')
      } else {
        // No opening message - just mark as ready to send onboarding
        setQueuedOpening({ content: '', audio_url: undefined })
        console.log('[DiscoveryChat] No opening message, will go straight to contextual response')
      }
    }).catch(err => {
      console.error('[DiscoveryChat] Failed to start session:', err)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]) // Reinitialize if userId changes

  // Send onboarding info automatically once connected
  useEffect(() => {
    console.log('[DiscoveryChat] Onboarding effect check:', {
      isConnected,
      hasOnboardingInfo: !!onboardingInfo,
      onboardingSent,
      hasQueuedOpening: !!queuedOpening,
      actualSessionId
    })

    if (isConnected && onboardingInfo && !onboardingSent && queuedOpening) {
      console.log('[DiscoveryChat] All conditions met, sending onboarding...')
      setOnboardingSent(true)

      // Small delay to ensure WebSocket is fully ready
      setTimeout(() => {
        console.log('[DiscoveryChat] Sending onboarding message now (silently)')

        // Send the user's onboarding/background info silently (not shown in chat UI)
        // The AI will use this context and respond with a contextual opening
        sendCommand(onboardingInfo)

        // Only add opening message if there's content (we skip the generic opener)
        if (queuedOpening.content && queuedOpening.content.trim()) {
          addMessage({
            id: crypto.randomUUID(),
            role: 'assistant',
            content: queuedOpening.content,
            audio_url: queuedOpening.audio_url,
          })

          // Auto-play opening if in audio mode
          if (isAudioMode && queuedOpening.audio_url) {
            playAudio(queuedOpening.audio_url)
          }
        }
      }, 100)
    }
  }, [isConnected, onboardingInfo, onboardingSent, queuedOpening, sendMessage, addMessage, isAudioMode, playAudio, actualSessionId])

  // Check for topic found
  useEffect(() => {
    const lastMessage = messages[messages.length - 1]
    if (lastMessage?.type === 'topic_found' && lastMessage.topic) {
      onTopicFound(lastMessage.topic)
    }
  }, [messages, onTopicFound])

  // Check for create_goal_panel - notify parent to create new goal panel
  useEffect(() => {
    const lastMessage = messages[messages.length - 1]
    if (lastMessage?.type === 'create_goal_panel' && onGoalAccepted && actualSessionId && lastMessage.goalData) {
      console.log('[DiscoveryChat] Creating goal panel:', lastMessage.goalData.goal)
      onGoalAccepted(lastMessage.goalData.goal, actualSessionId)
    }
  }, [messages, onGoalAccepted, actualSessionId])

  // Helper to find last index (since findLastIndex may not be available)
  const findLastIdx = (arr: any[], predicate: (item: any) => boolean): number => {
    for (let i = arr.length - 1; i >= 0; i--) {
      if (predicate(arr[i])) return i
    }
    return -1
  }

  // Check if there's a pending goal proposal (last goal_proposed message without a subsequent goal panel creation)
  const lastGoalProposedIndex = findLastIdx(messages, m => m.type === 'goal_proposed')
  const lastGoalPanelIndex = findLastIdx(messages, m => m.type === 'create_goal_panel' || m.type === 'goal_accepted')
  const hasPendingGoal = lastGoalProposedIndex > lastGoalPanelIndex && lastGoalProposedIndex >= 0

  // Track if we just accepted a goal (show continuation options)
  const lastGoalAcceptedIndex = findLastIdx(messages, m => 
    m.type === 'create_goal_panel' || m.content?.includes('[Accepted goal]') || m.content?.includes('in a new panel')
  )
  const hasRecentGoalAccepted = lastGoalAcceptedIndex >= 0 && lastGoalAcceptedIndex === messages.length - 1
  const [showContinuationOptions, setShowContinuationOptions] = useState(false)
  
  // Show continuation options after goal accepted
  useEffect(() => {
    if (hasRecentGoalAccepted) {
      setShowContinuationOptions(true)
    }
  }, [hasRecentGoalAccepted])

  // Handle goal accept/reject
  const handleAcceptGoal = () => {
    if (isConnected) {
      sendCommand('__ACCEPT_GOAL__')
    }
  }

  const handleRejectGoal = () => {
    if (isConnected) {
      sendCommand('__REJECT_GOAL__')
    }
  }

  // Handle continuation options after goal accepted
  const handleContinueThread = () => {
    setShowContinuationOptions(false)
    // Ask AI to continue exploring the current thread
    sendMessage("Let's continue exploring this thread further. What else can we uncover here?")
  }

  const handleProposeDirection = () => {
    setShowContinuationOptions(false)
    // Focus the input so user can type their new direction
    const input = document.querySelector('.text-input') as HTMLInputElement
    if (input) {
      input.focus()
      input.placeholder = "What would you like to explore next?"
    }
  }

  const handleAIPropose = () => {
    setShowContinuationOptions(false)
    // Send command to AI to propose a DIFFERENT topic - not related to already-accepted goals
    sendMessage("Suggest something completely different to explore - look at my background and interests for a topic that's unrelated to the goals I've already accepted. I want diverse learning areas, not variations of the same theme.")
  }

  // Handle speech recognition transcript
  useEffect(() => {
    if (transcript && !isListening) {
      handleSend(transcript)
    }
  }, [transcript, isListening])

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = (text?: string) => {
    const messageText = text || inputText.trim()
    if (!messageText || !isConnected) return

    sendMessage(messageText)
    setInputText('')
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleMicClick = () => {
    if (isListening) {
      stopListening()
    } else {
      startListening()
    }
  }

  return (
    <div className="discovery-with-feed">
      {/* Feed Panel */}
      {userId && (
        <FeedPanel
          userId={userId}
          contextType="exploration"
          userBackground={onboardingInfo}
          goalsSummary={
            messages
              .filter(m => m.type === 'goal_proposed' || m.type === 'create_goal_panel')
              .map(m => m.proposedGoal || m.goalData?.goal)
              .filter(Boolean)
              .join(', ') || undefined
          }
        />
      )}

      <div className="discovery-layout">
        {/* Chat Area */}
        <div className="chat-container">
          <AudioToggle isAudioMode={isAudioMode} onToggle={toggleAudioMode} />

        <div className="messages">
          {/* All messages in unified array */}
          {messages.map((msg, index) => (
            <div key={msg.id}>
              <MessageBubble
                role={msg.role}
                content={msg.content}
                audioUrl={msg.audio_url}
                isAudioMode={isAudioMode}
                onAudioPlay={() => msg.audio_url && playAudio(msg.audio_url)}
              />
              {/* Show goal confirmation buttons for pending goal proposals */}
              {msg.type === 'goal_proposed' && 
               msg.proposedGoal && 
               index === lastGoalProposedIndex && 
               hasPendingGoal && (
                <div className="goal-confirmation">
                  <div className="goal-confirmation-buttons">
                    <button 
                      className="goal-accept-btn"
                      onClick={handleAcceptGoal}
                      disabled={!isConnected}
                    >
                      Yes, let's explore this
                    </button>
                    <button 
                      className="goal-reject-btn"
                      onClick={handleRejectGoal}
                      disabled={!isConnected}
                    >
                      Not quite — keep exploring
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}

          {/* Status indicator */}
          {status && (
            <div className="status-indicator">
              <div className="status-spinner"></div>
              <span>{status}</span>
            </div>
          )}

          {/* Continuation options after goal accepted */}
          {showContinuationOptions && (
            <div className="continuation-options">
              <p className="continuation-prompt">What would you like to do next?</p>
              <div className="continuation-buttons">
                <button 
                  className="continuation-btn continue-thread"
                  onClick={handleContinueThread}
                >
                  Continue this thread
                </button>
                <button 
                  className="continuation-btn propose-direction"
                  onClick={handleProposeDirection}
                >
                  I'll propose a new direction
                </button>
                <button 
                  className="continuation-btn ai-propose"
                  onClick={handleAIPropose}
                >
                  AI suggestion
                </button>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <div className="input-area">
          {isAudioMode && isSpeechSupported ? (
            <button
              className={`mic-button ${isListening ? 'listening' : ''}`}
              onMouseDown={handleMicClick}
              disabled={!isConnected}
            >
              {isListening ? 'Listening...' : 'Hold to Speak'}
            </button>
          ) : (
            <div className="text-input-container">
              <input
                type="text"
                className="text-input"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Type your message..."
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
          )}
        </div>
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
