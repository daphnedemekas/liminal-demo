import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import DiscoveryChat from './DiscoveryChat'

// Mock the API module
vi.mock('../services/api', () => ({
  api: {
    startDiscoverySession: vi.fn().mockResolvedValue({
      session_id: 'test-session-id',
      is_resumed: false,
      conversation_history: [],
      opening_message: 'Welcome! What would you like to explore today?',
    }),
    getDiscoverySchema: vi.fn().mockResolvedValue({}),
  },
}))

// Mock the hooks
vi.mock('../hooks/useWebSocket', () => ({
  useWebSocket: () => ({
    messages: [],
    sendMessage: vi.fn(),
    sendCommand: vi.fn(),
    addMessage: vi.fn(),
    setMessages: vi.fn(),
    isConnected: true,
    status: null,
  }),
}))

vi.mock('../hooks/useAudio', () => ({
  useAudio: () => ({
    isAudioMode: false,
    isPlaying: false,
    toggleAudioMode: vi.fn(),
    playAudio: vi.fn(),
  }),
}))

vi.mock('../hooks/useSpeechRecognition', () => ({
  useSpeechRecognition: () => ({
    isListening: false,
    transcript: '',
    startListening: vi.fn(),
    stopListening: vi.fn(),
    isSupported: false,
    resetTranscript: vi.fn(),
  }),
}))

// Mock child components
vi.mock('./ProfilePanel', () => ({
  default: () => <div data-testid="profile-panel">Profile Panel</div>,
}))

vi.mock('./FeedPanel', () => ({
  default: () => <div data-testid="feed-panel">Feed Panel</div>,
}))

describe('DiscoveryChat', () => {
  const defaultProps = {
    modelConfig: { interviewer: 'test-model', ranker: 'test-model' },
    onboardingInfo: 'Test user background info',
    userId: 'test-user-123',
    onTopicFound: vi.fn(),
    onGoalAccepted: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render without crashing', async () => {
    render(<DiscoveryChat {...defaultProps} />)
    
    // Should show the profile panel
    await waitFor(() => {
      expect(screen.getByTestId('profile-panel')).toBeInTheDocument()
    })
  })

  it('should call startDiscoverySession on mount', async () => {
    const { api } = await import('../services/api')
    
    render(<DiscoveryChat {...defaultProps} />)
    
    await waitFor(() => {
      expect(api.startDiscoverySession).toHaveBeenCalledWith(
        defaultProps.modelConfig,
        undefined,  // No goal for exploration
        defaultProps.userId
      )
    })
  })

  it('should reinitialize on remount', async () => {
    const { api } = await import('../services/api')
    
    // First mount
    const { unmount } = render(<DiscoveryChat {...defaultProps} />)
    
    await waitFor(() => {
      expect(api.startDiscoverySession).toHaveBeenCalledTimes(1)
    })
    
    // Unmount
    unmount()
    
    // Remount
    render(<DiscoveryChat {...defaultProps} />)
    
    await waitFor(() => {
      // Should be called again on remount
      expect(api.startDiscoverySession).toHaveBeenCalledTimes(2)
    })
  })

  it('should show retry button on session error', async () => {
    const { api } = await import('../services/api')
    
    // Make API fail
    ;(api.startDiscoverySession as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('Connection failed')
    )
    
    render(<DiscoveryChat {...defaultProps} />)
    
    await waitFor(() => {
      expect(screen.getByText(/Failed to connect/i)).toBeInTheDocument()
    })
    
    expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument()
  })

  it('should restore messages when resuming session', async () => {
    const { api } = await import('../services/api')
    
    ;(api.startDiscoverySession as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      session_id: 'resumed-session',
      is_resumed: true,
      conversation_history: [
        { role: 'user', content: 'Background info' },
        { role: 'assistant', content: 'Hello! How can I help?' },
        { role: 'user', content: 'I want to learn about AI' },
        { role: 'assistant', content: 'Great topic! What aspect interests you?' },
      ],
    })
    
    render(<DiscoveryChat {...defaultProps} />)
    
    await waitFor(() => {
      expect(api.startDiscoverySession).toHaveBeenCalled()
    })
    
    // Note: Actual message display depends on useWebSocket mock
    // This test verifies the API call behavior
  })
})


