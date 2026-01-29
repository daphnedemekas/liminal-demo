import { useState, useEffect, useRef, useCallback } from 'react'
import { useWebSocket, Message } from '../hooks/useWebSocket'
import { useAudio } from '../hooks/useAudio'
import { useSpeechRecognition } from '../hooks/useSpeechRecognition'
import { api } from '../services/api'
import MessageBubble from './MessageBubble'
import ResizableSplitPane from './ResizableSplitPane'
import MobileViewSwitcher from './MobileViewSwitcher'
import ProfilePanel from './ProfilePanel'
import FeedPanel from './FeedPanel'
import AudioToggle from './AudioToggle'
import BreathingCircle from './BreathingCircle'
import ContextTab from './ContextTab'
import DraftTab from './DraftTab'
import TerminalTab from './TerminalTab'
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
  const [activeTab, setActiveTab] = useState<'context' | 'draft' | 'terminal'>('context')
  const [isGeneratingPath, setIsGeneratingPath] = useState(false)
  const [isMobile, setIsMobile] = useState(() => window.innerWidth <= 768)
  const [mobileView, setMobileView] = useState<string>('chat')
  const [feedCollapsed, setFeedCollapsed] = useState(false)
  const [profileCollapsed, setProfileCollapsed] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const initRef = useRef(false)

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 768)
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const { messages, sendMessage, sendCommand, isConnected, status, addMessage, setMessages, onSchemaUpdate } = useWebSocket(actualSessionId || '', 'discovery')
  
  // These must be after useWebSocket since they depend on messages
  const hasFirstAssistantMessage = messages.some((msg) => msg.role === 'assistant')
  const shouldShowSidePanels = isResumed || hasFirstAssistantMessage
  const { isAudioMode, isPlaying, toggleAudioMode, playAudio } = useAudio()
  const {
    isListening,
    transcript,
    getTranscript,
    startListening,
    stopListening,
    isSupported: isSpeechSupported,
    resetTranscript,
  } = useSpeechRecognition()

  // handleSend must be defined before any useEffect that depends on it
  const handleSend = useCallback((text?: string) => {
    const messageText = text || inputText.trim()
    if (!messageText || !isConnected) return

    // Include audio mode preference so backend knows to generate TTS
    sendMessage(messageText, isAudioMode)
    setInputText('')
  }, [inputText, isConnected, sendMessage, isAudioMode])

  // Handle manual learning path generation
  const handleGenerateLearningPath = useCallback(() => {
    if (!isConnected || isGeneratingPath) return
    
    setIsGeneratingPath(true)
    sendCommand('__GENERATE_LEARNING_PATH__')

    // Safety timeout — reset if no response after 60s
    setTimeout(() => {
      setIsGeneratingPath(false)
    }, 60000)
  }, [isConnected, isGeneratingPath, sendCommand])

  // Initialize or resume goal-specific session
  useEffect(() => {
    if (initRef.current) return
    initRef.current = true

    // Start/resume discovery session with user_id and goal_id
    api.startDiscoverySession(modelConfig, goal, userId, goalId).then((response) => {
      setActualSessionId(response.session_id)
      setIsResumed(response.is_resumed)
      
      // Load profile summary if available
      if (response.profile_summary) {
        setProfileSummary(response.profile_summary)
      }
      
      // If resuming, load the conversation history
      if (response.is_resumed && response.conversation_history?.length > 0) {
        let historyToRestore = response.conversation_history.filter((msg: any) => {
          // Skip user messages that look like onboarding (long background text)
          if (msg.role === 'user' && onboardingInfo) {
            const msgContent = msg.content || ''
            const onboardingContent = onboardingInfo || ''
            // If message matches onboarding or is very long background text, skip it
            if (msgContent === onboardingContent || 
                (msgContent.length > 100 && 
                 (msgContent.includes('interested') || msgContent.includes('background') || 
                  msgContent.toLowerCase().includes('do') && msgContent.toLowerCase().includes('interested')))) {
              return false
            }
          }
          return true
        })
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
    }).catch(_err => {})

    return () => {
      initRef.current = false
    }
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
      setOnboardingSent(true)
      setTimeout(() => {
        sendCommand(`__ONBOARDING__${onboardingInfo}`)
      }, 100)
    }
  }, [isConnected, initialized, isResumed, onboardingSent, onboardingInfo, messages.length, sendCommand])

  // Check for create_teaching_panel - notify parent to create new teaching panel
  useEffect(() => {
    const lastMessage = messages[messages.length - 1]
    if (lastMessage?.type === 'create_teaching_panel' && lastMessage.teachingCandidate) {
      const conversationHistory = messages
        .filter(m => m.role === 'user' || m.role === 'assistant')
        .map(m => ({ role: m.role, content: m.content }))
      const candidate = lastMessage.teachingCandidate
      const tc = {
        id: candidate.id,
        topic: candidate.topic,
        focus_question: candidate.focus_question || '',
        identified_gap: candidate.identified_gap || '',
        readiness_score: candidate.readiness_score ?? 0.5,
        goalConversationHistory: conversationHistory
      } as TeachingCandidate
      onTeachingCandidateAccepted(tc)
      // Persist to DB so it survives page refresh
      api.saveTeachingCandidates(goalId, [tc]).catch(err =>
        console.error('[GoalChat] Failed to persist teaching candidate:', err)
      )
    }
  }, [messages, onTeachingCandidateAccepted, goalId])

  // Check for task_curriculum_proposed or error - reset loading state
  useEffect(() => {
    const lastMessage = messages[messages.length - 1]
    if (lastMessage?.type === 'task_curriculum_proposed' || 
        (lastMessage?.role === 'assistant' && lastMessage?.content?.startsWith('⚠️'))) {
      setIsGeneratingPath(false)
    }
  }, [messages])

  // Check for task_curriculum_accepted - notify parent to add all tasks
  useEffect(() => {
    const lastMessage = messages[messages.length - 1]
    if (lastMessage?.type === 'task_curriculum_accepted' && lastMessage.tasks) {
      setIsGeneratingPath(false)
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
      // Also persist to DB as safety net (backend should have saved already)
      api.saveTeachingCandidates(goalId, tasksWithHistory).catch(err =>
        console.error('[GoalChat] Failed to persist curriculum:', err)
      )
    }
  }, [messages, onCurriculumAccepted])

  // Track if we've played audio for the current last message
  const [lastPlayedMessageId, setLastPlayedMessageId] = useState<string | null>(null)
  // Track when audio finished to add delay before recording
  const [audioEndTime, setAudioEndTime] = useState<number>(0)

  // Stop recording IMMEDIATELY when audio is about to play
  useEffect(() => {
    if (isPlaying && isListening) {
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
        // Capture transcript from ref BEFORE stopping (avoids stale closure)
        const currentTranscript = getTranscript()
        stopListening()

        // Send the transcript after stopping
        if (currentTranscript && currentTranscript.trim()) {
          handleSend(currentTranscript)
          resetTranscript()
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isListening, isAudioMode, stopListening, getTranscript, handleSend, resetTranscript])

  // Check for task curriculum proposed (new batch proposal flow)
  const lastCurriculumProposedIndex = messages.map((m, i) => m.type === 'task_curriculum_proposed' ? i : -1).filter(i => i >= 0).pop() ?? -1
  const lastCurriculumAcceptedIndex = messages.map((m, i) => m.type === 'task_curriculum_accepted' ? i : -1).filter(i => i >= 0).pop() ?? -1
  const hasPendingCurriculum = lastCurriculumProposedIndex > lastCurriculumAcceptedIndex && lastCurriculumProposedIndex >= 0
  // @ts-ignore - unused for now, may be needed later
  const _pendingCurriculumProposal = hasPendingCurriculum ? messages[lastCurriculumProposedIndex] : null

  // Handle task curriculum accept/modify
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

  const chatContent = (
    <div className="goal-chat" style={{ position: 'relative', height: '100%' }}>
      <BreathingCircle
        isVisible={isAudioMode}
        isAISpeaking={isPlaying}
        isUserRecording={isListening && !status}
        isProcessing={!!status || messages.length === 0}
        onTap={() => {
          if (status || messages.length === 0) return
          if (isListening) {
            const currentTranscript = getTranscript()
            stopListening()
            if (currentTranscript && currentTranscript.trim()) {
              handleSend(currentTranscript)
              resetTranscript()
            }
          } else if (!isPlaying) {
            startListening()
          }
        }}
        onExit={toggleAudioMode}
        statusText={isListening && !status ? transcript : undefined}
      />

      <div className="goal-chat-header">
        <div className="goal-chat-title">
          <span className="goal-icon"></span>
          <h2>{goal}</h2>
        </div>
        <div className="goal-chat-header-actions">
          <div className="goal-chat-status">
            {isResumed && <span className="resumed-badge" title="Session resumed">Resumed</span>}
            {status ? (
              <span className="status-indicator-small" title={status}>
                <span className="status-dot"></span>
                {status}
              </span>
            ) : isConnected ? (
              <span className="connected-indicator" title="Connected">●</span>
            ) : (
              <span className="connecting-indicator" title="Connecting...">○</span>
            )}
          </div>
        </div>
      </div>

      <div className="goal-chat-messages" style={{ position: 'relative' }}>
        {messages.map((msg, index) => (
          <div key={msg.id}>
            {msg.type !== 'task_curriculum_proposed' && (
              <MessageBubble
                role={msg.role}
                content={msg.content}
                audioUrl={msg.audio_url}
                isAudioMode={isAudioMode}
                onAudioPlay={() => msg.audio_url && playAudio(msg.audio_url)}
              />
            )}
            {msg.type === 'task_curriculum_proposed' &&
             index === lastCurriculumProposedIndex &&
             hasPendingCurriculum && (
              <div className="curriculum-confirmation">
                {msg.curriculum && msg.curriculum.tasks && msg.curriculum.tasks.length > 0 && (
                  <div className="curriculum-tasks-preview">
                    <h4>Project Path ({msg.curriculum.tasks.length} steps)</h4>
                    <ol className="curriculum-tasks-list">
                      {msg.curriculum.tasks.map((task: any, idx: number) => (
                        <li key={task.id || idx} className={`curriculum-task-item ${task.status || (idx === 0 ? 'available' : 'locked')}`}>
                          <strong>{task.topic || `Task ${idx + 1}`}</strong>
                          {task.justification && (
                            <p className="task-justification">{task.justification}</p>
                          )}
                          {task.status && (
                            <span className={`task-status ${task.status}`}>{task.status}</span>
                          )}
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
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
            <AudioToggle isAudioMode={isAudioMode} onToggle={toggleAudioMode} />
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
  )

  const tabsContent = (
    <div className="goal-tabs-area" style={{ height: '100%' }}>
      <div className="goal-tabs-nav">
        <button className={`goal-tab-btn ${activeTab === 'context' ? 'active' : ''}`} onClick={() => setActiveTab('context')}>Context</button>
        <button className={`goal-tab-btn ${activeTab === 'draft' ? 'active' : ''}`} onClick={() => setActiveTab('draft')}>Documents</button>
        <button className={`goal-tab-btn ${activeTab === 'terminal' ? 'active' : ''}`} onClick={() => setActiveTab('terminal')}>Terminal</button>
      </div>
      <div className="goal-tab-content">
        {activeTab === 'context' && <ContextTab goalId={goalId} userId={userId} />}
        {activeTab === 'draft' && <DraftTab goalId={goalId} userId={userId} onSendToChat={handleSend} />}
        {activeTab === 'terminal' && <TerminalTab goalId={goalId} userId={userId} />}
      </div>
    </div>
  )

  const profileContent = shouldShowSidePanels && (
    <ProfilePanel
      sessionId={actualSessionId}
      isConnected={isConnected}
      initialSummary={profileSummary}
      onSchemaUpdate={onSchemaUpdate}
      onGeneratePath={handleGenerateLearningPath}
      isGeneratingPath={isGeneratingPath}
      onTeachingCandidateClick={(candidate) => {
        onTeachingCandidateAccepted({
          id: candidate.id,
          topic: candidate.topic,
          focus_question: candidate.focus_question || '',
          identified_gap: candidate.identified_gap || '',
          readiness_score: candidate.readiness_score ?? 0.5,
          goalConversationHistory: messages
            .filter(m => m.role === 'user' || m.role === 'assistant')
            .map(m => ({ role: m.role, content: m.content }))
        } as TeachingCandidate)
      }}
    />
  )

  const feedContent = shouldShowSidePanels && (
    <FeedPanel
      userId={userId}
      contextType="goal"
      goalId={goalId}
      goalText={goal}
      userBackground={onboardingInfo}
    />
  )

  if (isMobile) {
    return (
      <div className="mobile-fullscreen-container">
        <div className="mobile-fullscreen-view">
          {mobileView === 'chat' && chatContent}
          {mobileView === 'workspace' && tabsContent}
          {mobileView === 'insights' && (
            <div className="mobile-insights-view">
              {profileContent}
              {feedContent}
            </div>
          )}
        </div>
        <MobileViewSwitcher
          activeView={mobileView}
          views={[
            { key: 'chat', label: 'Chat' },
            { key: 'workspace', label: 'Workspace' },
            { key: 'insights', label: 'Insights' },
          ]}
          onViewChange={setMobileView}
        />
      </div>
    )
  }

  return (
    <div className={`discovery-with-feed ${feedCollapsed ? 'feed-collapsed' : ''} ${profileCollapsed ? 'profile-collapsed' : ''}`}>
      {!feedCollapsed && feedContent}

      <div className="goal-chat-layout">
        <div className="goal-chat-main-area">
          <ResizableSplitPane
            initialTopHeight={50}
            minTopHeight={20}
            maxTopHeight={80}
            top={chatContent}
            bottom={tabsContent}
          />
        </div>

        {!profileCollapsed && profileContent}
      </div>

      {/* Panel toggle buttons */}
      <button
        className={`panel-toggle panel-toggle-left ${feedCollapsed ? 'collapsed' : ''}`}
        onClick={() => setFeedCollapsed(c => !c)}
        title={feedCollapsed ? 'Show feed' : 'Hide feed'}
      >
        {feedCollapsed ? '▶' : '◀'}
      </button>
      <button
        className={`panel-toggle panel-toggle-right ${profileCollapsed ? 'collapsed' : ''}`}
        onClick={() => setProfileCollapsed(c => !c)}
        title={profileCollapsed ? 'Show progress' : 'Hide progress'}
      >
        {profileCollapsed ? '◀' : '▶'}
      </button>
    </div>
  )
}
