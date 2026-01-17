import { useState, useEffect, useRef } from 'react'
import { useWebSocket, Message } from '../hooks/useWebSocket'
import { useAudio } from '../hooks/useAudio'
import { api } from '../services/api'
import MessageBubble from './MessageBubble'
import ProfilePanel from './ProfilePanel'
import FeedPanel from './FeedPanel'
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
}

export default function GoalChat({ 
  goalId,
  goal, 
  userId,
  modelConfig, 
  onboardingInfo,
  onTeachingCandidateAccepted 
}: GoalChatProps) {
  const [inputText, setInputText] = useState('')
  const [actualSessionId, setActualSessionId] = useState<string | null>(null)
  const [initialized, setInitialized] = useState(false)
  const [isResumed, setIsResumed] = useState(false)
  const [profileSummary, setProfileSummary] = useState<string | undefined>(undefined)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const initRef = useRef(false)

  const { messages, sendMessage, sendCommand, isConnected, status, addMessage, setMessages } = useWebSocket(actualSessionId || '', 'discovery')
  const { isAudioMode, playAudio } = useAudio()

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
        const restoredMessages: Message[] = response.conversation_history.map((msg: any, idx: number) => ({
          id: `restored-${idx}`,
          role: msg.role as 'user' | 'assistant',
          content: msg.content,
        }))
        setMessages(restoredMessages)
        
        // Refresh history after a short delay to catch any in-flight saves
        // (handles race condition when navigating away during long processing)
        setTimeout(async () => {
          try {
            const freshData = await api.startDiscoverySession(modelConfig, goal, userId, goalId)
            if (freshData.conversation_history?.length > response.conversation_history.length) {
              console.log('[GoalChat] Found newer history:', freshData.conversation_history.length, 'messages')
              const freshMessages: Message[] = freshData.conversation_history.map((msg: any, idx: number) => ({
                id: `restored-fresh-${idx}`,
                role: msg.role as 'user' | 'assistant',
                content: msg.content,
              }))
              setMessages(freshMessages)
            }
          } catch (err) {
            console.error('[GoalChat] Failed to refresh history:', err)
          }
        }, 2000)  // Wait 2 seconds for any pending saves to complete
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

  // Send onboarding info once connected (only for new sessions)
  // Use sendCommand to send silently - don't show onboarding in chat UI
  const [onboardingSent, setOnboardingSent] = useState(false)
  useEffect(() => {
    if (isConnected && initialized && !isResumed && !onboardingSent && onboardingInfo && messages.length <= 1) {
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

  // Check for teaching candidate proposed
  const lastTeachingProposedIndex = messages.findLastIndex(m => m.type === 'teaching_proposed')
  const lastTeachingPanelIndex = messages.findLastIndex(m => m.type === 'create_teaching_panel' || m.type === 'teaching_accepted')
  const hasPendingTeaching = lastTeachingProposedIndex > lastTeachingPanelIndex && lastTeachingProposedIndex >= 0
  const pendingTeachingProposal = hasPendingTeaching ? messages[lastTeachingProposedIndex] : null

  // Handle teaching candidate accept/reject
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

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = () => {
    const messageText = inputText.trim()
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
        <div className="goal-chat">
          {/* Goal Header */}
          <div className="goal-chat-header">
          <div className="goal-chat-title">
            <span className="goal-icon"></span>
            <h2>{goal}</h2>
          </div>
          <div className="goal-chat-status">
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
        <div className="goal-chat-messages">
          {messages.map((msg, index) => (
            <div key={msg.id}>
              <MessageBubble
                role={msg.role}
                content={msg.content}
                audioUrl={msg.audio_url}
                isAudioMode={isAudioMode}
                onAudioPlay={() => msg.audio_url && playAudio(msg.audio_url)}
              />
              {/* Show teaching candidate confirmation buttons */}
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

        {/* Input */}
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
              onClick={handleSend}
              disabled={!inputText.trim() || !isConnected}
            >
              Send
            </button>
          </div>
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
