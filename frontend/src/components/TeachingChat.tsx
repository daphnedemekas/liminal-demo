import { useState, useEffect, useRef } from 'react'
import MessageBubble from './MessageBubble'
import FeedPanel from './FeedPanel'

interface TeachingCandidate {
  id: number
  topic: string
  focus_question: string
  identified_gap: string
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
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Initialize with a helpful opening message
  useEffect(() => {
    const openingMessage: Message = {
      id: 'opening',
      role: 'assistant',
      content: `Let's explore **${candidate.topic}** together.\n\n${candidate.focus_question}\n\nFeel free to ask questions, share what you're confused about, or tell me what aspect interests you most.`
    }
    setMessages([openingMessage])
  }, [candidate])

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
      // Simple teaching conversation - no discovery, just helpful responses
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
          user_background: onboardingInfo
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
    <div className="teaching-chat-layout">
      {/* Chat Panel */}
      <div className="teaching-chat-container">
        <div className="teaching-chat-header">
          <div className="teaching-topic">
            <span className="teaching-label">Learning:</span>
            <span className="teaching-title">{candidate.topic}</span>
          </div>
          <div className="teaching-context">
            <span className="goal-context">Part of: {goalText}</span>
          </div>
        </div>

        <div className="messages-container">
          {messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              role={msg.role}
              content={msg.content}
            />
          ))}
          {isLoading && (
            <div className="loading-indicator">
              <span>Thinking...</span>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="input-container">
          <textarea
            className="text-input"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask a question or share what you're confused about..."
            rows={2}
          />
          <button 
            className="send-button" 
            onClick={handleSend}
            disabled={isLoading || !inputText.trim()}
          >
            Send
          </button>
        </div>
      </div>

      {/* Feed Panel */}
      <FeedPanel
        sessionId={`teaching-${candidate.id}`}
        contextType="teaching_candidate"
        contextId={String(candidate.id)}
        goalText={goalText}
        teachingTopic={candidate.topic}
      />
    </div>
  )
}

