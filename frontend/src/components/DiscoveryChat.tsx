import { useState, useEffect, useRef, useCallback } from 'react'
import { useWebSocket } from '../hooks/useWebSocket'
import { useAudio } from '../hooks/useAudio'
import { useSpeechRecognition } from '../hooks/useSpeechRecognition'
import { api } from '../services/api'
import MessageBubble from './MessageBubble'
import AudioToggle from './AudioToggle'
import BreathingCircle from './BreathingCircle'
import ProfilePanel from './ProfilePanel'
import FeedPanel from './FeedPanel'
import { ModelConfig } from './ModelSelector'

interface DiscoveryChatProps {
  modelConfig: ModelConfig
  onboardingInfo: string
  userId?: string  // For persistent sessions
  onTopicFound: (topic: any) => void
  onGoalAccepted?: (goal: string, sessionId: string) => void
  onBackgroundCollected?: (info: string) => void  // Called when user provides background in chat
}

export default function DiscoveryChat({ modelConfig, onboardingInfo, userId, onTopicFound, onGoalAccepted, onBackgroundCollected }: DiscoveryChatProps) {
  const [inputText, setInputText] = useState('')
  const [actualSessionId, setActualSessionId] = useState<string | null>(null)
  const [onboardingSent, setOnboardingSent] = useState(false)
  const [profileSummary, setProfileSummary] = useState<string | undefined>(undefined)
  const [queuedOpening, setQueuedOpening] = useState<{ content: string; audio_url?: string } | null>(null)
  const [sessionError, setSessionError] = useState<string | null>(null)
  const [retryCount, setRetryCount] = useState(0)
  const [awaitingBackground, setAwaitingBackground] = useState(false)  // True when we're waiting for user's background info
  const initRef = useRef(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const { messages, sendMessage, sendCommand, isConnected, status, addMessage, setMessages } = useWebSocket(actualSessionId || '', 'discovery')
  
  // These must be after useWebSocket since they depend on messages
  // Count assistant messages - need at least 2 (background prompt + response) before showing panels
  const assistantMessageCount = messages.filter((msg) => msg.role === 'assistant').length
  const userMessageCount = messages.filter((msg) => msg.role === 'user').length
  // Show panels only after first exchange is complete (user sent background AND got response)
  const shouldShowSidePanels = assistantMessageCount >= 2 || (assistantMessageCount >= 1 && userMessageCount >= 1 && !status)
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
  const handleSend = useCallback(async (text?: string) => {
    const messageText = text || inputText.trim()
    if (!messageText || !isConnected) return

    // If we're awaiting background info, this is the first real exchange
    if (awaitingBackground) {
      setAwaitingBackground(false)
      
      // Save background info via API for the user profile
      if (userId) {
        try {
          await api.updateOnboarding(userId, messageText)
          console.log('[DiscoveryChat] Saved background info to user profile')
        } catch (err) {
          console.error('[DiscoveryChat] Failed to save background info:', err)
        }
      }
      
      // Notify parent component so Feed/Profile panels appear
      if (onBackgroundCollected) {
        onBackgroundCollected(messageText)
      }
      
      // Note: Don't call addMessage here - sendMessage already adds the user message to UI
    }

    // Send to backend via WebSocket (this saves to conversation history and adds to UI)
    // Include audio mode preference so backend knows to generate TTS
    sendMessage(messageText, isAudioMode)
    setInputText('')
  }, [inputText, isConnected, sendMessage, isAudioMode, awaitingBackground, userId, onBackgroundCollected, addMessage])

  // Reset initRef when component unmounts to allow re-initialization on remount
  useEffect(() => {
    return () => {
      console.log('[DiscoveryChat] Component unmounting, resetting init flag')
      initRef.current = false
    }
  }, [])

  // Initialize session and get opening message
  useEffect(() => {
    console.log('[DiscoveryChat] Component mounted, initializing session...')

    // React 18 StrictMode runs effects twice in dev; guard so we don't double-create sessions / duplicate messages.
    // But allow retry if we have an error
    if (initRef.current && !sessionError) {
      console.log('[DiscoveryChat] Already initialized, skipping')
      return
    }
    initRef.current = true
    setSessionError(null)

    console.log('[DiscoveryChat] Starting discovery session with model config:', modelConfig, 'userId:', userId)

    // Pass userId for persistence (no goal for exploration)
    api.startDiscoverySession(modelConfig, undefined, userId).then((response) => {
      console.log('[DiscoveryChat] Session response:', {
        session_id: response.session_id,
        is_resumed: response.is_resumed,
        history_length: response.conversation_history?.length || 0
      })
      setActualSessionId(response.session_id)
      setSessionError(null)

      // Load profile summary if available
      if (response.profile_summary) {
        setProfileSummary(response.profile_summary)
      }
      
      // If resuming, always restore conversation history and show options for how to continue
      if (response.is_resumed && response.conversation_history?.length > 0) {
        console.log('[DiscoveryChat] Resuming with', response.conversation_history.length, 'messages')
        // Always restore messages first - they should never disappear
        const restoredMessages = response.conversation_history.map((msg: any, idx: number) => ({
          id: `restored-${idx}`,
          role: msg.role as 'user' | 'assistant',
          content: msg.content,
        }))
        // Add welcome back message as the latest assistant message
        const welcomeMessage = {
          id: 'welcome-back',
          role: 'assistant' as const,
          content: 'Welcome back! How would you like to continue?',
          type: 'resume_options' as const,
        }
        setMessages([...restoredMessages, welcomeMessage])
        setOnboardingSent(true)  // Don't re-send onboarding for resumed sessions
        setQueuedOpening({ content: '', audio_url: undefined })  // No need for opening
      } else if (!onboardingInfo) {
        // No onboarding info yet - show prompt asking for background
        const backgroundPrompt = "Before we begin exploring, tell me a bit about yourself - what do you do, what are you interested in, and what's been on your mind lately?"
        setAwaitingBackground(true)
        setOnboardingSent(true)  // Don't trigger automatic onboarding send
        setQueuedOpening({ content: backgroundPrompt, audio_url: undefined })
        console.log('[DiscoveryChat] No onboarding info, showing background prompt')
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
      setSessionError('Failed to connect to the server. Please try again.')
      initRef.current = false  // Allow retry
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, retryCount]) // Reinitialize if userId changes or retry requested

  // Show background prompt when waiting for user to provide background
  useEffect(() => {
    if (isConnected && awaitingBackground && queuedOpening?.content && messages.length === 0) {
      console.log('[DiscoveryChat] Showing background prompt to user')
      addMessage({
        id: 'background-prompt',
        role: 'assistant',
        content: queuedOpening.content,
      })
    }
  }, [isConnected, awaitingBackground, queuedOpening, messages.length, addMessage])

  // Send onboarding info automatically once connected (when we have background info)
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

        // Only add opening message if there's content AND we're not awaiting background
        // (if awaiting background, the prompt was already shown)
        if (queuedOpening.content && queuedOpening.content.trim() && !awaitingBackground) {
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
  }, [isConnected, onboardingInfo, onboardingSent, queuedOpening, sendCommand, sendMessage, addMessage, isAudioMode, playAudio, actualSessionId, awaitingBackground])

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
    // 4. Audio ended too recently (give 1.5s buffer to avoid echo)
    const hasPendingAudio = lastMessage?.role === 'assistant' && lastMessage?.audio_url && lastMessage.id !== lastPlayedMessageId
    const isProcessing = !!status
    const timeSinceAudioEnd = Date.now() - audioEndTime
    const audioJustEnded = audioEndTime > 0 && timeSinceAudioEnd < 1500
    
    if (isAudioMode && !isPlaying && !isListening && isSpeechSupported && !hasPendingAudio && !isProcessing && !audioJustEnded) {
      const timer = setTimeout(() => {
        // Double-check we're still not playing
        if (!isPlaying) {
          console.log('[Voice] Starting recording after audio finished')
          startListening()
        }
      }, 500)
      return () => clearTimeout(timer)
    }
    
    // If audio just ended, schedule a check for when the delay is over
    if (isAudioMode && !isPlaying && !isListening && isSpeechSupported && !hasPendingAudio && !isProcessing && audioJustEnded) {
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

  // Auto-scroll to bottom
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
      {/* Feed Panel - show after first assistant message */}
      {userId && onboardingInfo && shouldShowSidePanels && (
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
        <div className="chat-container" style={{ position: 'relative' }}>
          <AudioToggle isAudioMode={isAudioMode} onToggle={toggleAudioMode} />

          {/* Voice Mode Overlay - covers the chat panel */}
          <BreathingCircle 
            isVisible={isAudioMode} 
            isAISpeaking={isPlaying}
            isUserRecording={isListening && !status}
            isProcessing={!!status}
            onTap={() => {
              if (status) {
                // Don't do anything while processing
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
            statusText={isListening ? transcript : undefined}
          />

        <div className="messages" style={{ position: 'relative' }}>

          {/* All messages in unified array */}
          {messages.map((msg, index) => {
            const isLastResumeOptions = msg.id === 'welcome-back' && index === messages.length - 1
            return (
              <div key={msg.id}>
                <MessageBubble
                  role={msg.role}
                  content={msg.content}
                  audioUrl={msg.audio_url}
                  isAudioMode={isAudioMode}
                  isUserRecording={isListening}
                  onAudioPlay={() => msg.audio_url && playAudio(msg.audio_url)}
                />
                {/* Show resume options buttons for welcome back message */}
                {isLastResumeOptions && (
                  <div className="resume-options">
                    <div className="resume-options-buttons">
                      <button
                        className="resume-option-btn"
                        onClick={() => {
                          // Continue on this thread - let AI continue the conversation
                          // Remove the resume options message and send continuation message
                          setMessages(prev => prev.filter(m => m.id !== 'welcome-back'))
                          sendMessage("Let's continue from where we left off", isAudioMode)
                        }}
                        disabled={!isConnected}
                      >
                        Continue on this thread
                      </button>
                      <button
                        className="resume-option-btn"
                        onClick={() => {
                          // Suggest a new direction - send message asking for new direction
                          setMessages(prev => prev.filter(m => m.id !== 'welcome-back'))
                          sendMessage("I'd like to explore a new direction", isAudioMode)
                        }}
                        disabled={!isConnected}
                      >
                        Suggest a new direction
                      </button>
                      <button
                        className="resume-option-btn"
                        onClick={() => {
                          // AI suggests something - ask AI to suggest what to explore next
                          setMessages(prev => prev.filter(m => m.id !== 'welcome-back'))
                          sendMessage("What should we explore next?", isAudioMode)
                        }}
                        disabled={!isConnected}
                      >
                        AI suggests something
                      </button>
                    </div>
                  </div>
                )}
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
            )
          })}

          {/* Status indicator */}
          {status && (
            <div className="status-indicator">
              <div className="status-spinner"></div>
              <span>{status}</span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Error display with retry button */}
        {sessionError && (
          <div className="session-error">
            <p>{sessionError}</p>
            <button 
              className="retry-button"
              onClick={() => setRetryCount(c => c + 1)}
            >
              Retry Connection
            </button>
          </div>
        )}

        {/* Input area - hidden in voice mode since overlay handles it */}
        {!isAudioMode && !sessionError && (
          <div className="input-area">
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
          </div>
        )}
      </div>

        {/* Profile Panel - show after first assistant message */}
        {onboardingInfo && shouldShowSidePanels && (
          <ProfilePanel 
            sessionId={actualSessionId} 
            isConnected={isConnected} 
            initialSummary={profileSummary}
            onGoalSelected={onGoalAccepted ? (goalText) => {
              if (actualSessionId) {
                onGoalAccepted(goalText, actualSessionId)
              }
            } : undefined}
          />
        )}
      </div>
    </div>
  )
}
