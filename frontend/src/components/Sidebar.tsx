import { useState } from 'react'

export interface TeachingCandidate {
  id: number
  topic: string
  focus_question: string
  identified_gap: string
  readiness_score: number
}

export interface GoalSession {
  id: string  // Display ID (can be same as goalId)
  goalId: number  // Database goal ID for API calls
  goal: string
  createdAt: Date
  isActive: boolean
  hasTeachingCandidate: boolean
  teachingCandidate?: TeachingCandidate
}

interface SidebarProps {
  goalSessions: GoalSession[]
  activeSessionId: string | null
  onSelectSession: (sessionId: string | null) => void
  onNewExploration: () => void
  isExplorationActive: boolean
  username?: string
  onLogout?: () => void
}

export default function Sidebar({ 
  goalSessions, 
  activeSessionId, 
  onSelectSession, 
  onNewExploration,
  isExplorationActive,
  username,
  onLogout
}: SidebarProps) {
  const [isCollapsed, setIsCollapsed] = useState(false)

  return (
    <div className={`sidebar ${isCollapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-header">
        <h2 className="sidebar-title">
          {isCollapsed ? 'Goals' : 'Learning Goals'}
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
              <span className="sidebar-exploration-icon"></span>
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
                  <button
                    key={session.id}
                    className={`sidebar-session ${activeSessionId === session.id ? 'active' : ''}`}
                    onClick={() => onSelectSession(session.id)}
                  >
                    <div className="sidebar-session-content">
                      <span className="sidebar-session-icon">
                        {session.hasTeachingCandidate ? 'Done' : 'Active'}
                      </span>
                      <div className="sidebar-session-info">
                        <span className="sidebar-session-goal">{session.goal}</span>
                        <span className="sidebar-session-date">
                          {new Date(session.createdAt).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                  </button>
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

