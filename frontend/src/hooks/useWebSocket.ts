import { useState, useEffect, useRef, useCallback } from 'react'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  audio_url?: string
  type?: 'message' | 'topic_found' | 'learning_message' | 'goal_proposed' | 'goal_accepted' | 'teaching_proposed' | 'teaching_accepted' | 'create_goal_panel' | 'create_teaching_panel' | 'task_curriculum_proposed' | 'task_curriculum_accepted'
  topic?: any
  proposedGoal?: string  // For goal_proposed type
  goalData?: {  // For create_goal_panel type
    goal: string
    goal_id: string
    message: string
  }
  teachingCandidate?: {  // For teaching_proposed and create_teaching_panel types
    id: number
    topic: string
    focus_question: string
    identified_gap: string
    readiness_score?: number
  }
  curriculum?: {  // For task_curriculum_proposed type
    tasks: Array<{
      id: number
      topic: string
      justification: string
      prerequisites: number[]
      status: string
    }>
    overall_justification?: string
  }
  tasks?: Array<any>  // For task_curriculum_accepted type - accepted tasks
  isStreaming?: boolean
}

interface UseWebSocketReturn {
  messages: Message[]
  sendMessage: (content: string) => void
  sendCommand: (command: string) => void  // Send without showing in UI
  addMessage: (message: Message) => void
  setMessages: (messages: Message[]) => void  // For restoring history
  isConnected: boolean
  status: string | null
}

export function useWebSocket(sessionId: string, phase: 'discovery' | 'learning'): UseWebSocketReturn {
  const [messages, setMessages] = useState<Message[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const streamingMessageIdRef = useRef<string | null>(null)
  const retryCountRef = useRef(0)
  const maxRetries = 3
  const connectionTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  // Connect to WebSocket with timeout and retry
  useEffect(() => {
    // Don't connect if sessionId is empty
    if (!sessionId) {
      return
    }

    let retryTimeout: NodeJS.Timeout | null = null
    let isMounted = true

    const connect = () => {
      if (!isMounted) return
      
      const wsBase = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'
      const wsUrl = `${wsBase}/ws/${phase}/${sessionId}`
      
      console.log(`[WebSocket] Connecting to ${phase}... (attempt ${retryCountRef.current + 1})`)
      setStatus('Connecting...')
      
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      // Connection timeout - 5 seconds
      connectionTimeoutRef.current = setTimeout(() => {
        if (ws.readyState !== WebSocket.OPEN && isMounted) {
          console.log('[WebSocket] Connection timeout, closing...')
          ws.close()
          
          // Retry if under max retries
          if (retryCountRef.current < maxRetries) {
            retryCountRef.current++
            setStatus(`Retrying... (${retryCountRef.current}/${maxRetries})`)
            retryTimeout = setTimeout(connect, 1000)
          } else {
            setStatus('Connection failed. Please refresh.')
          }
        }
      }, 5000)

      ws.onopen = () => {
        console.log(`[WebSocket] Connected: ${phase}`)
        if (connectionTimeoutRef.current) clearTimeout(connectionTimeoutRef.current)
        retryCountRef.current = 0
        setIsConnected(true)
        setStatus(null)
      }

      ws.onmessage = (event) => {
        console.log('[useWebSocket] Received message:', event.data.substring(0, 100) + '...')
        const data = JSON.parse(event.data)
        console.log('[useWebSocket] Parsed data type:', data.type)

        // Handle error messages
        if (data.type === 'error') {
          console.error('[WebSocket] Error from server:', data.message)
          // Show error as a system message
          const errorMessage: Message = {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: `⚠️ ${data.message}`,
          }
          setMessages(prev => [...prev, errorMessage])
          setStatus(null)
          return
        }

        // Handle status messages
        if (data.type === 'status') {
          setStatus(data.status)
          return
        }

        // Handle streaming messages
        if (data.type === 'stream_start') {
          // Create a new streaming message placeholder
          const messageId = crypto.randomUUID()
          streamingMessageIdRef.current = messageId
          setStatus(null)
          
          const streamingMessage: Message = {
            id: messageId,
            role: 'assistant',
            content: '',
            isStreaming: true,
          }
          setMessages(prev => [...prev, streamingMessage])
          return
        }

        if (data.type === 'stream_chunk') {
          // Append chunk to the current streaming message
          if (streamingMessageIdRef.current) {
            setMessages(prev => prev.map(msg => 
              msg.id === streamingMessageIdRef.current
                ? { ...msg, content: msg.content + data.content }
                : msg
            ))
          }
          return
        }

        if (data.type === 'stream_end') {
          // Finalize the streaming message with audio
          if (streamingMessageIdRef.current) {
            setMessages(prev => prev.map(msg => 
              msg.id === streamingMessageIdRef.current
                ? { ...msg, content: data.content, audio_url: data.audio_url, isStreaming: false }
                : msg
            ))
            streamingMessageIdRef.current = null
          }
          return
        }

        // Clear status when we get a real message
        setStatus(null)

        // Handle goal_proposed - show confirmation UI
        if (data.type === 'goal_proposed') {
          const goalMessage: Message = {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: data.content || data.message,
            audio_url: data.audio_url,
            type: 'goal_proposed',
            proposedGoal: data.goal,
          }
          setMessages(prev => [...prev, goalMessage])
          return
        }

        // Handle goal_accepted - transition to phase 2
        if (data.type === 'goal_accepted') {
          const acceptedMessage: Message = {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: data.content,
            type: 'goal_accepted',
          }
          setMessages(prev => [...prev, acceptedMessage])
          return
        }

        // Handle task_curriculum_proposed - show curriculum with Accept/Modify buttons
        if (data.type === 'task_curriculum_proposed') {
          const curriculumMessage: Message = {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: data.content || data.message,
            audio_url: data.audio_url,
            type: 'task_curriculum_proposed',
            curriculum: data.curriculum,
          }
          setMessages(prev => [...prev, curriculumMessage])
          return
        }

        // Handle task_curriculum_accepted - curriculum confirmed
        if (data.type === 'task_curriculum_accepted') {
          const acceptedMessage: Message = {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: data.content || 'Curriculum accepted! Starting with the first topic.',
            type: 'task_curriculum_accepted',
            tasks: data.tasks  // Include the accepted tasks
          }
          setMessages(prev => [...prev, acceptedMessage])
          return
        }

        // Handle teaching_proposed - show confirmation UI for teaching candidate (legacy single-candidate)
        if (data.type === 'teaching_proposed') {
          const teachingMessage: Message = {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: data.content || data.message,
            audio_url: data.audio_url,
            type: 'teaching_proposed',
            teachingCandidate: data.candidate,
          }
          setMessages(prev => [...prev, teachingMessage])
          return
        }

        // Handle teaching_accepted - ready to start learning
        if (data.type === 'teaching_accepted') {
          const acceptedMessage: Message = {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: data.content,
            type: 'teaching_accepted',
          }
          setMessages(prev => [...prev, acceptedMessage])
          return
        }

        // Handle create_goal_panel - new message type for multi-panel architecture
        if (data.type === 'create_goal_panel') {
          const panelMessage: Message = {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: data.message,
            type: 'create_goal_panel',
            goalData: {
              goal: data.goal,
              goal_id: data.goal_id,
              message: data.message,
            },
          }
          setMessages(prev => [...prev, panelMessage])
          return
        }

        // Handle create_teaching_panel - new message type for multi-panel architecture
        if (data.type === 'create_teaching_panel') {
          const panelMessage: Message = {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: data.message,
            type: 'create_teaching_panel',
            teachingCandidate: data.candidate,
          }
          setMessages(prev => [...prev, panelMessage])
          return
        }

        // Handle topic_found (may come after streaming)
        if (data.type === 'topic_found') {
          // If we were streaming, update that message
          if (streamingMessageIdRef.current) {
            setMessages(prev => prev.map(msg => 
              msg.id === streamingMessageIdRef.current
                ? { ...msg, content: data.content, audio_url: data.audio_url, type: 'topic_found', topic: data.topic, isStreaming: false }
                : msg
            ))
            streamingMessageIdRef.current = null
          } else {
            // Otherwise add as new message
            const newMessage: Message = {
              id: crypto.randomUUID(),
              role: 'assistant',
              content: data.content,
              audio_url: data.audio_url,
              type: data.type,
              topic: data.topic,
            }
            setMessages(prev => [...prev, newMessage])
          }
          return
        }

        // Handle regular messages (non-streaming fallback)
        const newMessage: Message = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: data.content,
          audio_url: data.audio_url,
          type: data.type,
          topic: data.topic,
        }

        setMessages(prev => [...prev, newMessage])
      }

      ws.onerror = (error) => {
        console.error('[WebSocket] Error:', error)
      }

      ws.onclose = () => {
        console.log('[WebSocket] Disconnected')
        setIsConnected(false)
      }
    }

    connect()

    return () => {
      isMounted = false
      if (connectionTimeoutRef.current) clearTimeout(connectionTimeoutRef.current)
      if (retryTimeout) clearTimeout(retryTimeout)
      retryCountRef.current = 0
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [sessionId, phase])

  // Send message function
  const sendMessage = useCallback((content: string) => {
    console.log('[useWebSocket] sendMessage called:', {
      hasWs: !!wsRef.current,
      readyState: wsRef.current?.readyState,
      isOpen: wsRef.current?.readyState === WebSocket.OPEN,
      contentLength: content.length
    })

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      console.log('[useWebSocket] Sending message to server...')
      // Add user message to UI immediately
      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content,
      }
      setMessages(prev => [...prev, userMessage])

      // Send to server
      wsRef.current.send(JSON.stringify({ content }))
    } else {
      console.error('[useWebSocket] Cannot send - WebSocket not ready!', {
        current: wsRef.current,
        readyState: wsRef.current?.readyState
      })
    }
  }, [])

  // Add message function (for adding messages without sending to server)
  const addMessage = useCallback((message: Message) => {
    setMessages(prev => [...prev, message])
  }, [])

  // Send command without showing in UI (for internal commands like __ACCEPT_GOAL__)
  const sendCommand = useCallback((command: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      console.log('[useWebSocket] Sending command:', command)
      wsRef.current.send(JSON.stringify({ content: command }))
    } else {
      console.error('[useWebSocket] Cannot send command - WebSocket not ready!')
    }
  }, [])

  return {
    messages,
    sendMessage,
    sendCommand,
    addMessage,
    setMessages,
    isConnected,
    status,
  }
}
