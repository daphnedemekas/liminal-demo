import { useState, useEffect } from 'react'
import { stripMarkdown } from '../utils/textUtils'

export type TaskStatus = 'locked' | 'available' | 'in_progress' | 'completed'

export interface TeachingCandidate {
  id: number
  topic: string
  focus_question: string
  identified_gap: string
  readiness_score: number
  status: TaskStatus  // locked, available, in_progress, completed
  goalConversationHistory?: Array<{ role: string; content: string }>  // Context from goal chat
}

export interface GoalSession {
  id: string  // Display ID (can be same as goalId)
  goalId: number  // Database goal ID for API calls
  goal: string
  createdAt: Date
  isActive: boolean
  teachingCandidates: TeachingCandidate[]  // Multiple teaching candidates per goal
}

interface SidebarProps {
  goalSessions: GoalSession[]
  activeSessionId: string | null
  activeTeachingId: number | null  // Currently selected teaching candidate
  isTrajectoryActive?: boolean
  onSelectTrajectory?: () => void
  onSelectSession: (sessionId: string | null) => void
  onSelectTeaching: (goalSessionId: string, teachingId: number) => void  // Select a teaching candidate
  onNewExploration: () => void
  isExplorationActive: boolean
  onCreatePath?: () => void  // Create a new learning path directly
  username?: string
  onLogout?: () => void
  // Model selection
  currentModel?: string
  onModelChange?: (model: string) => void
}

export default function Sidebar({ 
  goalSessions, 
  activeSessionId, 
  activeTeachingId,
  isTrajectoryActive = false,
  onSelectTrajectory,
  onSelectSession, 
  onSelectTeaching,
  onNewExploration,
  isExplorationActive,
  onCreatePath,
  username,
  onLogout,
  currentModel = 'openai:gpt-4o',
  onModelChange
}: SidebarProps) {
  const [isCollapsed, setIsCollapsed] = useState(() => window.innerWidth <= 768)
  const [expandedGoals, setExpandedGoals] = useState<Set<string>>(() => {
    // Auto-expand goals that have teaching candidates
    return new Set(goalSessions.filter(s => s.teachingCandidates.length > 0).map(s => s.id))
  })

  // Auto-close sidebar on mobile after navigation
  const isMobile = () => window.innerWidth <= 768
  const autoClose = () => { if (isMobile()) setIsCollapsed(true) }

  // Auto-expand goals when they get new teaching candidates
  useEffect(() => {
    const withCandidates = goalSessions.filter(s => s.teachingCandidates.length > 0).map(s => s.id)
    if (withCandidates.length > 0) {
      setExpandedGoals(prev => {
        const next = new Set(prev)
        withCandidates.forEach(id => next.add(id))
        return next
      })
    }
  }, [goalSessions])

  const toggleGoalExpanded = (goalId: string) => {
    setExpandedGoals(prev => {
      const next = new Set(prev)
      if (next.has(goalId)) {
        next.delete(goalId)
      } else {
        next.add(goalId)
      }
      return next
    })
  }

  return (
    <div className={`sidebar ${isCollapsed ? 'collapsed' : ''}`}>
      {/* Mobile overlay backdrop */}
      {!isCollapsed && (
        <div className="sidebar-backdrop" onClick={() => setIsCollapsed(true)} />
      )}
      <div className="sidebar-header">
        <h2 className="sidebar-title">
          <span className="sidebar-title-full">Liminal</span>
          <span className="sidebar-title-short">L</span>
        </h2>
        <button
          className="sidebar-toggle"
          onClick={() => setIsCollapsed(!isCollapsed)}
          title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {isCollapsed ? '☰' : '←'}
        </button>
      </div>

      {!isCollapsed && (
        <>
          {/* Trajectory Section */}
          <div className="sidebar-section">
            <div className="sidebar-section-label">Trajectory</div>
            <button
              className={`sidebar-exploration-btn ${isTrajectoryActive ? 'active' : ''}`}
              onClick={() => { onSelectTrajectory?.(); autoClose() }}
              disabled={!onSelectTrajectory}
              title={!onSelectTrajectory ? 'Project history unavailable' : 'View your project history'}
            >
              <span className="sidebar-exploration-icon"></span>
              <span>Project Journeys</span>
            </button>
          </div>

          {/* Exploration Section */}
          <div className="sidebar-section">
            <div className="sidebar-section-label">Exploration</div>
            <button 
              className={`sidebar-exploration-btn ${isExplorationActive ? 'active' : ''}`}
              onClick={() => { onNewExploration(); autoClose() }}
            >
              <span className="sidebar-exploration-icon"></span>
              <span>Current Exploration</span>
            </button>
          </div>

          {/* Goals Section */}
          <div className="sidebar-section">
            <div className="sidebar-section-label">
              <span>Paths</span>
              {onCreatePath && (
                <button
                  className="sidebar-add-btn"
                  onClick={onCreatePath}
                  title="Start a new project"
                >
                  +
                </button>
              )}
            </div>
            <div className="sidebar-sessions">
              {goalSessions.length === 0 ? (
                <div className="sidebar-empty">
                  <p className="sidebar-hint">Your projects will appear here as you explore.</p>
                </div>
              ) : (
                goalSessions.map((session) => (
                  <div key={session.id} className="sidebar-goal-group">
                    {/* Goal Header */}
                    <div 
                      className={`sidebar-session ${activeSessionId === session.id && !activeTeachingId ? 'active' : ''}`}
                    >
                      <button
                        className="sidebar-session-main"
                        onClick={() => { onSelectSession(session.id); autoClose() }}
                      >
                        <span className="sidebar-session-icon"></span>
                        <div className="sidebar-session-info">
                          <span className="sidebar-session-goal">{session.goal}</span>
                          <span className="sidebar-session-date">
                            {new Date(session.createdAt).toLocaleDateString()}
                          </span>
                        </div>
                      </button>
                      {session.teachingCandidates.length > 0 && (
                        <button 
                          className="sidebar-expand-btn"
                          onClick={(e) => {
                            e.stopPropagation()
                            toggleGoalExpanded(session.id)
                          }}
                        >
                          {expandedGoals.has(session.id) ? '▼' : '▶'}
                        </button>
                      )}
                    </div>

                    {/* Deep Dives (sub-items) - Project Steps */}
                    {expandedGoals.has(session.id) && session.teachingCandidates.length > 0 && (
                      <div className="sidebar-teaching-list">
                        {session.teachingCandidates.map((tc, idx) => {
                          const isLocked = tc.status === 'locked'
                          const isCompleted = tc.status === 'completed'
                          const isInProgress = tc.status === 'in_progress'
                          
                          return (
                            <button
                              key={tc.id}
                              className={`sidebar-teaching-item ${activeTeachingId === tc.id ? 'active' : ''} ${isLocked ? 'locked' : ''} ${isCompleted ? 'completed' : ''} ${isInProgress ? 'in-progress' : ''}`}
                              onClick={() => { if (!isLocked) { onSelectTeaching(session.id, tc.id); autoClose() } }}
                              disabled={isLocked}
                              title={isLocked ? 'Complete previous tasks to unlock' : stripMarkdown(tc.topic)}
                            >
                              <span className="sidebar-teaching-status">
                                {isLocked && '🔒'}
                                {isCompleted && '✓'}
                                {isInProgress && '▶'}
                                {tc.status === 'available' && `${idx + 1}`}
                              </span>
                              <span className="sidebar-teaching-topic">{stripMarkdown(tc.topic)}</span>
                            </button>
                          )
                        })}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}

      {/* Model Selector */}
      {!isCollapsed && onModelChange && (
        <div className="sidebar-model-selector">
          <select 
            value={currentModel} 
            onChange={(e) => onModelChange(e.target.value)}
            className="model-dropdown"
          >
            <option value="openai:gpt-4o">GPT-4o</option>
            <option value="openai:gpt-4o-mini">GPT-4o Mini</option>
            <option value="anthropic:claude-sonnet-4-20250514">Claude Sonnet 4</option>
            <option value="anthropic:claude-3-5-haiku-20241022">Claude Haiku 3.5</option>
            <option value="cerebras:llama-3.3-70b">Llama 3.3 70B</option>
          </select>
        </div>
      )}

      {/* User Footer */}
      {!isCollapsed && username && (
        <div className="sidebar-footer">
          <div className="sidebar-user">
            <span className="sidebar-user-name">{username}</span>
          </div>
          {onLogout && (
            <button className="sidebar-logout-btn" onClick={onLogout}>
              Logout
            </button>
          )}
        </div>
      )}
    </div>
  )
}
