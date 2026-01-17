import { useState, useEffect, useRef } from 'react'
import { useWebSocket } from '../hooks/useWebSocket'
import { useAudio } from '../hooks/useAudio'
import { useSpeechRecognition } from '../hooks/useSpeechRecognition'
import { api } from '../services/api'
import MessageBubble from './MessageBubble'
import AudioToggle from './AudioToggle'

interface LearningChatProps {
  sessionId: string
}

export default function LearningChat({ sessionId }: LearningChatProps) {
  const [inputText, setInputText] = useState('')
  const [openingMessage, setOpeningMessage] = useState<string | null>(null)
  const [openingAudioUrl, setOpeningAudioUrl] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const { messages, sendMessage, isConnected } = useWebSocket(sessionId, 'learning')
  const { isAudioMode, toggleAudioMode, playAudio } = useAudio()
  const {
    isListening,
    transcript,
    startListening,
    stopListening,
    isSupported: isSpeechSupported,
  } = useSpeechRecognition()

  // Initialize learning session
  useEffect(() => {
    api.startLearningSession(sessionId).then((response) => {
      setOpeningMessage(response.opening_message)
      setOpeningAudioUrl(response.audio_url || null)

      // Auto-play opening if in audio mode
      if (isAudioMode && response.audio_url) {
        playAudio(response.audio_url)
      }
    })
  }, [sessionId])

  // Handle speech recognition transcript
  useEffect(() => {
    if (transcript && !isListening) {
      handleSend(transcript)
    }
  }, [transcript, isListening])

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, openingMessage])

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
    <div className="chat-container">
      <AudioToggle isAudioMode={isAudioMode} onToggle={toggleAudioMode} />

      <div className="messages">
        {/* Opening message */}
        {openingMessage && (
          <MessageBubble
            role="assistant"
            content={openingMessage}
            audioUrl={openingAudioUrl || undefined}
            isAudioMode={isAudioMode}
            onAudioPlay={() => openingAudioUrl && playAudio(openingAudioUrl)}
          />
        )}

        {/* Conversation messages */}
        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            role={msg.role}
            content={msg.content}
            audioUrl={msg.audio_url}
            isAudioMode={isAudioMode}
            onAudioPlay={() => msg.audio_url && playAudio(msg.audio_url)}
          />
        ))}

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
  )
}
