import { useState } from 'react'

export interface TeachingCandidate {
  id: number
  topic: string
  focus_question: string
  identified_gap: string
  readiness_score: number
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
  onSelectSession: (sessionId: string | null) => void
  onSelectTeaching: (goalSessionId: string, teachingId: number) => void  // Select a teaching candidate
  onNewExploration: () => void
  isExplorationActive: boolean
  username?: string
  onLogout?: () => void
}

export default function Sidebar({ 
  goalSessions, 
  activeSessionId, 
  activeTeachingId,
  onSelectSession, 
  onSelectTeaching,
  onNewExploration,
  isExplorationActive,
  username,
  onLogout
}: SidebarProps) {
  const [isCollapsed, setIsCollapsed] = useState(false)
  const [expandedGoals, setExpandedGoals] = useState<Set<string>>(new Set())

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
      <div className="sidebar-header">
        <h2 className="sidebar-title">
          {isCollapsed ? 'L' : 'Learning Goals'}
        </h2>
        <button 
          className="sidebar-toggle"
          onClick={() => setIsCollapsed(!isCollapsed)}
          title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {isCollapsed ? '→' : '←'}
        </button>
      </div>

      {!isCollapsed && (
        <>
          {/* Exploration Section */}
          <div className="sidebar-section">
            <div className="sidebar-section-label">Exploration</div>
            <button 
              className={`sidebar-exploration-btn ${isExplorationActive ? 'active' : ''}`}
              onClick={onNewExploration}
            >
              <span className="sidebar-exploration-icon">🔭</span>
              <span>Current Exploration</span>
            </button>
          </div>

          {/* Goals Section */}
          <div className="sidebar-section">
            <div className="sidebar-section-label">Learning Goals</div>
            <div className="sidebar-sessions">
              {goalSessions.length === 0 ? (
                <div className="sidebar-empty">
                  <p className="sidebar-hint">Goals will appear here as you explore.</p>
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
                        onClick={() => onSelectSession(session.id)}
                      >
                        <span className="sidebar-session-icon">🎯</span>
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

                    {/* Teaching Candidates (sub-items) */}
                    {expandedGoals.has(session.id) && session.teachingCandidates.length > 0 && (
                      <div className="sidebar-teaching-list">
                        {session.teachingCandidates.map((tc) => (
                          <button
                            key={tc.id}
                            className={`sidebar-teaching-item ${activeTeachingId === tc.id ? 'active' : ''}`}
                            onClick={() => onSelectTeaching(session.id, tc.id)}
                          >
                            <span className="sidebar-teaching-icon">📚</span>
                            <span className="sidebar-teaching-topic">{tc.topic}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </>
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
