import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useWebSocket } from './useWebSocket'

describe('useWebSocket', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('should not connect when sessionId is empty', () => {
    const { result } = renderHook(() => useWebSocket('', 'discovery'))
    
    expect(result.current.isConnected).toBe(false)
    expect(result.current.status).toBe(null)
  })

  it('should connect when sessionId is provided', async () => {
    const { result } = renderHook(() => useWebSocket('test-session-123', 'discovery'))
    
    // Initially connecting
    expect(result.current.isConnected).toBe(false)
    expect(result.current.status).toBe('Connecting...')
    
    // Fast forward past the mock connection delay
    await act(async () => {
      vi.advanceTimersByTime(50)
    })
    
    expect(result.current.isConnected).toBe(true)
    expect(result.current.status).toBe(null)
  })

  it('should initialize with empty messages', () => {
    const { result } = renderHook(() => useWebSocket('test-session', 'discovery'))
    
    expect(result.current.messages).toEqual([])
  })

  it('should add user message when sendMessage is called', async () => {
    const { result } = renderHook(() => useWebSocket('test-session', 'discovery'))
    
    // Wait for connection
    await act(async () => {
      vi.advanceTimersByTime(50)
    })
    
    act(() => {
      result.current.sendMessage('Hello, world!')
    })
    
    expect(result.current.messages).toHaveLength(1)
    expect(result.current.messages[0].role).toBe('user')
    expect(result.current.messages[0].content).toBe('Hello, world!')
  })

  it('should allow adding messages manually', () => {
    const { result } = renderHook(() => useWebSocket('test-session', 'discovery'))
    
    act(() => {
      result.current.addMessage({
        id: 'test-id',
        role: 'assistant',
        content: 'Test message',
      })
    })
    
    expect(result.current.messages).toHaveLength(1)
    expect(result.current.messages[0].content).toBe('Test message')
  })

  it('should allow setting messages (for history restore)', () => {
    const { result } = renderHook(() => useWebSocket('test-session', 'discovery'))
    
    const historyMessages = [
      { id: '1', role: 'assistant' as const, content: 'Message 1' },
      { id: '2', role: 'user' as const, content: 'Message 2' },
      { id: '3', role: 'assistant' as const, content: 'Message 3' },
    ]
    
    act(() => {
      result.current.setMessages(historyMessages)
    })
    
    expect(result.current.messages).toHaveLength(3)
    expect(result.current.messages[2].content).toBe('Message 3')
  })

  it('should disconnect when sessionId changes', async () => {
    const { result, rerender } = renderHook(
      ({ sessionId }) => useWebSocket(sessionId, 'discovery'),
      { initialProps: { sessionId: 'session-1' } }
    )
    
    // Wait for initial connection
    await act(async () => {
      vi.advanceTimersByTime(50)
    })
    
    expect(result.current.isConnected).toBe(true)
    
    // Change sessionId
    rerender({ sessionId: 'session-2' })
    
    // Old connection should close, new one should start
    expect(result.current.isConnected).toBe(false)
    
    await act(async () => {
      vi.advanceTimersByTime(50)
    })
    
    expect(result.current.isConnected).toBe(true)
  })
})

describe('useWebSocket connection timeout', () => {
  it('should show retry status on timeout', async () => {
    // Create a mock WebSocket that never opens
    class SlowWebSocket {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3
      
      readyState = SlowWebSocket.CONNECTING
      onopen: ((ev: Event) => void) | null = null
      onclose: ((ev: CloseEvent) => void) | null = null
      
      constructor(public url: string) {
        // Never opens
      }
      
      send(_data: string) {}
      
      close() {
        this.readyState = SlowWebSocket.CLOSED
        if (this.onclose) {
          this.onclose(new CloseEvent('close'))
        }
      }
    }
    
    // @ts-ignore
    global.WebSocket = SlowWebSocket
    
    vi.useFakeTimers()
    
    const { result } = renderHook(() => useWebSocket('test-session', 'discovery'))
    
    // Initially connecting
    expect(result.current.status).toBe('Connecting...')
    
    // Fast forward past 5s timeout
    await act(async () => {
      vi.advanceTimersByTime(5000)
    })
    
    // Should be retrying
    expect(result.current.status).toBe('Retrying... (1/3)')
    
    vi.useRealTimers()
  })
})


