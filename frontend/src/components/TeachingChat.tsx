import { useState, useEffect, useRef } from 'react'
import MessageBubble from './MessageBubble'
import ProfilePanel from './ProfilePanel'
import FeedPanel from './FeedPanel'

interface TeachingCandidate {
  id: number
  topic: string
  focus_question: string
  identified_gap: string
  goalConversationHistory?: Array<{ role: string; content: string }>
}

interface TeachingChatProps {
  candidate: TeachingCandidate
  goalId: number
  goalText: string
  userId: string
  onboardingInfo: string
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
}

export default function TeachingChat({ 
  candidate, 
  goalId, 
  goalText,
  userId,
  onboardingInfo 
}: TeachingChatProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [inputText, setInputText] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [isInitialized, setIsInitialized] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const initRef = useRef(false)

  // Initialize with a structured opening that references the goal conversation
  useEffect(() => {
    if (initRef.current) return
    initRef.current = true

    const initializeTeaching = async () => {
      setIsLoading(true)
      try {
        // Request structured opening from backend with goal context
        const response = await fetch('http://localhost:8000/api/teaching/start', {
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
            user_background: onboardingInfo
          })
        })

        if (response.ok) {
          const data = await response.json()
          setSessionId(data.session_id)
          
          // Add the structured opening message
          const openingMessage: Message = {
            id: 'opening',
            role: 'assistant',
            content: data.opening_message
          }
          setMessages([openingMessage])
        } else {
          // Fallback opening if backend fails
          const fallbackMessage: Message = {
            id: 'opening',
            role: 'assistant',
            content: `Let's explore **${candidate.topic}** together.\n\n${candidate.focus_question}\n\nFeel free to ask questions or tell me what aspect interests you most.`
          }
          setMessages([fallbackMessage])
        }
      } catch (error) {
        console.error('Failed to initialize teaching session:', error)
        const fallbackMessage: Message = {
          id: 'opening',
          role: 'assistant',
          content: `Let's explore **${candidate.topic}** together.\n\n${candidate.focus_question}\n\nFeel free to ask questions or tell me what aspect interests you most.`
        }
        setMessages([fallbackMessage])
      } finally {
        setIsLoading(false)
        setIsInitialized(true)
      }
    }

    initializeTeaching()
  }, [candidate, goalId, goalText, userId, onboardingInfo])

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    if (!inputText.trim() || isLoading) return

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: inputText.trim()
    }
    
    setMessages(prev => [...prev, userMessage])
    setInputText('')
    setIsLoading(true)

    try {
      const response = await fetch('http://localhost:8000/api/teaching/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          goal_id: goalId,
          teaching_candidate_id: candidate.id,
          topic: candidate.topic,
          identified_gap: candidate.identified_gap,
          focus_question: candidate.focus_question,
          message: userMessage.content,
          conversation_history: messages.map(m => ({ role: m.role, content: m.content })),
          user_background: onboardingInfo,
          goal_conversation_history: candidate.goalConversationHistory || []
        })
      })

      if (response.ok) {
        const data = await response.json()
        const assistantMessage: Message = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: data.response
        }
        setMessages(prev => [...prev, assistantMessage])
      } else {
        throw new Error('Failed to get response')
      }
    } catch (error) {
      console.error('Teaching chat error:', error)
      const errorMessage: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: "I'm having trouble responding right now. Please try again."
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

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
        <div className="goal-chat">
          {/* Header */}
          <div className="goal-chat-header">
            <div className="goal-chat-title">
              <span className="goal-icon">📚</span>
              <h2>{candidate.topic}</h2>
            </div>
            <div className="goal-chat-status">
              <span className="goal-context-badge">Part of: {goalText}</span>
              {isLoading && !isInitialized && (
                <span className="status-indicator-small">
                  <span className="status-dot"></span>
                  Preparing...
                </span>
              )}
            </div>
          </div>

          {/* Messages */}
          <div className="goal-chat-messages">
            {messages.map((msg) => (
              <MessageBubble
                key={msg.id}
                role={msg.role}
                content={msg.content}
              />
            ))}
            {isLoading && (
              <div className="status-indicator">
                <div className="status-spinner"></div>
                <span>Thinking...</span>
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
                placeholder="Ask a question or share what you're confused about..."
                disabled={isLoading}
              />
              <button
                className="send-button"
                onClick={handleSend}
                disabled={!inputText.trim() || isLoading}
              >
                Send
              </button>
            </div>
          </div>
        </div>

        {/* Profile Panel - Right side */}
        <ProfilePanel 
          sessionId={sessionId} 
          isConnected={isInitialized}
        />
      </div>
    </div>
  )
}
