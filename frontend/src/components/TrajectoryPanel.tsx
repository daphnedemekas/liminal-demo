import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, LearnerTrajectoryDashboard, UserData } from '../services/api'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'

interface TrajectoryPanelProps {
  userId: string
}

type GraphNode = {
  id: string
  label: string
  type: 'root' | 'goal' | 'task'
  goalId?: number
  sessionId?: string
  status?: string
}

type ViewLevel = 'goals' | 'teachings' | 'detail'

export default function TrajectoryPanel({ userId }: TrajectoryPanelProps) {
  // Core data
  const [data, setData] = useState<LearnerTrajectoryDashboard | null>(null)
  const [userData, setUserData] = useState<UserData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Navigation state
  const [viewLevel, setViewLevel] = useState<ViewLevel>('goals')
  const [selectedNodeId, setSelectedNodeId] = useState<string>('root')
  const [selectedGoalId, setSelectedGoalId] = useState<number | null>(null)
  const [selectedTeachingId, setSelectedTeachingId] = useState<string | null>(null)

  // Level-specific data
  const [goalProgressData, setGoalProgressData] = useState<any>(null)
  const [teachingDetailData, setTeachingDetailData] = useState<any>(null)

  // Load trajectory dashboard
  const load = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const [d, u] = await Promise.all([
        api.getTrajectory(userId),
        api.getUserData(userId),
      ])
      setData(d)
      setUserData(u)

      // Auto-refresh if empty
      if (d && (!d.goals || d.goals.length === 0)) {
        console.log('[Trajectory] No goals found, triggering auto-refresh...')
        try {
          const refreshed = await api.refreshTrajectory(userId)
          console.log('[Trajectory] Auto-refresh successful, goals:', refreshed.goals?.length || 0)
          setData(refreshed)
        } catch (refreshError) {
          console.error('[Trajectory] Auto-refresh failed:', refreshError)
        }
      } else {
        console.log('[Trajectory] Loaded with', d.goals?.length || 0, 'goals')
      }
    } catch (e: any) {
      setError(e?.message || 'Failed to load project history')
    } finally {
      setIsLoading(false)
    }
  }, [userId])

  const refresh = useCallback(async () => {
    setIsLoading(true)
    try {
      const refreshed = await api.refreshTrajectory(userId)
      setData(refreshed)
    } catch (e: any) {
      setError(e?.message || 'Failed to refresh')
    } finally {
      setIsLoading(false)
    }
  }, [userId])

  // Fetch goal progress when selected
  const fetchGoalProgress = useCallback(async (goalId: number) => {
    try {
      const response = await fetch(`/api/goal/${goalId}/progress?user_id=${userId}`)
      const data = await response.json()
      setGoalProgressData(data)
    } catch (e) {
      console.error('Failed to fetch goal progress:', e)
    }
  }, [userId])

  // Fetch curriculum for each goal to show progress
  // @ts-ignore - unused for now, may be needed later
  const _fetchGoalCurriculums = useCallback(async (goalIds: number[]) => {
    const curriculums: Record<number, any> = {}
    await Promise.all(
      goalIds.map(async (goalId) => {
        try {
          const response = await fetch(`/api/goal/${goalId}/progress?user_id=${userId}`)
          const data = await response.json()
          if (data.curriculum) {
            curriculums[goalId] = data.curriculum
          }
        } catch (e) {
          console.error(`Failed to fetch curriculum for goal ${goalId}:`, e)
        }
      })
    )
    return curriculums
  }, [userId])

  // Fetch teaching detail when selected
  const fetchTeachingDetail = useCallback(async (sessionId: string) => {
    try {
      const response = await fetch(`/api/teaching/${sessionId}/detail?user_id=${userId}`)
      const data = await response.json()
      setTeachingDetailData(data)
    } catch (e) {
      console.error('Failed to fetch teaching detail:', e)
    }
  }, [userId])

  // Effect to load data on level changes
  useEffect(() => {
    if (viewLevel === 'teachings' && selectedGoalId) {
      fetchGoalProgress(selectedGoalId)
    }
  }, [viewLevel, selectedGoalId, fetchGoalProgress])

  useEffect(() => {
    if (viewLevel === 'detail' && selectedTeachingId) {
      fetchTeachingDetail(selectedTeachingId)
    }
  }, [viewLevel, selectedTeachingId, fetchTeachingDetail])

  useEffect(() => {
    load()
  }, [load])

  // Build graph nodes
  const graphNodes = useMemo<GraphNode[]>(() => {
    const nodes: GraphNode[] = []
    nodes.push({
      id: 'root',
      label: 'Dashboard',
      type: 'root',
    })

    const goals = userData?.goals || []
    goals.forEach((goal) => {
      nodes.push({
        id: `goal-${goal.id}`,
        label: goal.goal_text,
        type: 'goal',
        goalId: goal.id,
        status: goal.status,
      })

      // For teachings, we'd need session data - skipping for now in graph
      // Can be populated when we have session info
    })

    return nodes
  }, [userData])

  // Handle node click
  const handleNodeClick = (node: GraphNode) => {
    setSelectedNodeId(node.id)

    if (node.type === 'root') {
      setViewLevel('goals')
      setSelectedGoalId(null)
      setSelectedTeachingId(null)
    } else if (node.type === 'goal') {
      setViewLevel('teachings')
      setSelectedGoalId(node.goalId || null)
      setSelectedTeachingId(null)
    } else if (node.type === 'task') {
      setViewLevel('detail')
      setSelectedTeachingId(node.sessionId || null)
    }
  }

  const updated_at = data?.updated_at

  if (error) {
    return (
      <div className="trajectory-panel">
        <div className="profile-card warning-card">
          <p>Error: {error}</p>
          <button onClick={load}>Retry</button>
        </div>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="trajectory-panel">
        <div className="loading">Loading project history...</div>
      </div>
    )
  }

  return (
    <div className="trajectory-panel">
      <div className="trajectory-panel-header">
        <h1 className="panel-title">Dashboard</h1>
        {updated_at && (
          <span className="last-updated-badge">
            Updated {new Date(updated_at).toLocaleString()}
          </span>
        )}
        <button onClick={refresh} className="refresh-button">
          Refresh
        </button>
      </div>

      <div className="trajectory-panel-content">
        <div className="trajectory-grid">
          {/* Left Column: Graph */}
          <div className="trajectory-graph">
            <div className="profile-card">
              <div className="card-header">
                <span className="card-title">Project Graph</span>
                <span className="item-count">{graphNodes.length}</span>
              </div>
              <div className="graph-tree">
                {graphNodes.map(node => (
                  <button
                    key={node.id}
                    className={`graph-node ${node.type} ${selectedNodeId === node.id ? 'active' : ''}`}
                    onClick={() => handleNodeClick(node)}
                  >
                    <span className="graph-node-label">{node.label}</span>
                    {node.status && (
                      <span className={`graph-node-status ${node.status}`}>
                        {node.status}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Right Column: Dynamic View Based on Level */}
          <div className="trajectory-details">
            {viewLevel === 'goals' && (
              <GoalsCardView
                goals={data?.goals || []}
                userData={userData}
                userId={userId}
                onGoalClick={(goalId: number) => {
                  setSelectedGoalId(goalId)
                  setViewLevel('teachings')
                }}
              />
            )}

            {viewLevel === 'teachings' && (
              <TeachingsCardView
                goalData={goalProgressData}
                onTeachingClick={(sessionId: string) => {
                  setSelectedTeachingId(sessionId)
                  setViewLevel('detail')
                }}
                onBack={() => setViewLevel('goals')}
              />
            )}

            {viewLevel === 'detail' && (
              <TeachingDetailView
                detailData={teachingDetailData}
                onBack={() => setViewLevel('teachings')}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ============================================
// Level 1: Goals Card View
// ============================================

function GoalsCardView({ goals, userData, userId, onGoalClick }: any) {
  const [curriculums, setCurriculums] = useState<Record<number, any>>({})
  // @ts-ignore - unused for now, may be needed later
  const [_loadingCurriculums, setLoadingCurriculums] = useState(false)

  useEffect(() => {
    if (goals && goals.length > 0) {
      setLoadingCurriculums(true)
      Promise.all(
        goals.map(async (goal: any) => {
          try {
            const response = await fetch(`/api/goal/${goal.goal_id}/progress?user_id=${userId}`)
            const data = await response.json()
            if (data.curriculum && data.curriculum.length > 0) {
              return { goalId: goal.goal_id, curriculum: data.curriculum }
            }
          } catch (e) {
            console.error(`Failed to fetch curriculum for goal ${goal.goal_id}:`, e)
          }
          return null
        })
      ).then(results => {
        const curriculumsMap: Record<number, any> = {}
        results.forEach(result => {
          if (result) {
            curriculumsMap[result.goalId] = result.curriculum
          }
        })
        setCurriculums(curriculumsMap)
        setLoadingCurriculums(false)
      })
    }
  }, [goals, userId])

  if (!goals || goals.length === 0) {
    return (
      <div className="profile-card empty-state">
        <p>No learning goals yet. Start a conversation to create your first goal!</p>
      </div>
    )
  }

  return (
    <div className="goals-grid">
      {goals.map((goal: any) => {
        const narrative = generateGoalNarrative(goal, userData)
        const curriculum = curriculums[goal.goal_id] || []
        const curriculumProgress = curriculum.length > 0 ? {
          total: curriculum.length,
          completed: curriculum.filter((t: any) => t.status === 'completed' || t.status === 'available').length
        } : null

        return (
          <div
            key={goal.goal_id}
            className="goal-card profile-card clickable"
            onClick={() => onGoalClick(goal.goal_id)}
          >
            <div className="card-header">
              <span className="card-title">{goal.goal_text}</span>
              <span className={`readiness-badge ${goal.momentum || 'active'}`}>
                {goal.momentum || 'active'}
              </span>
            </div>

            {/* Visual Progress Indicator */}
            {curriculumProgress && (
              <div className="goal-progress-visual">
                <div className="progress-bar-container">
                  <div 
                    className="progress-bar-fill" 
                    style={{ width: `${(curriculumProgress.completed / curriculumProgress.total) * 100}%` }}
                  />
                </div>
                <div className="progress-label">
                  <span>{curriculumProgress.completed} of {curriculumProgress.total} topics</span>
                </div>
              </div>
            )}

            <div className="goal-narrative">
              <p className="summary-text">{narrative}</p>
            </div>

            <div className="goal-current-state">
              <h4>Your Path</h4>
              <p>{goal.next_suggested_move || 'Ready to dive in!'}</p>
            </div>

            {goal.last_activity_at && (
              <div className="goal-metrics">
                <div className="metric-row">
                  <span className="metric-label">Last Activity</span>
                  <span className="metric-value">
                    {formatRelativeTime(goal.last_activity_at)}
                  </span>
                </div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function generateGoalNarrative(goal: any, userData: any): string {
  // Use the learning_summary if it's available and meaningful
  // The backend now generates insightful descriptions based on conversation history
  if (goal.learning_summary && goal.learning_summary.trim()) {
    return goal.learning_summary
  }
  
  // Fallback to generic description only if learning_summary is missing
  const curiosityType = userData?.curiosity_type?.value || 'interest'
  const curiosityText = curiosityType === 'interest'
    ? "You're drawn to this because it genuinely fascinates you."
    : "You want to fill a knowledge gap that's been nagging you."

  return `${curiosityText} We're building a path that matches your learning style.`
}

function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  // Handle edge cases: same day, future dates, or invalid dates
  if (isNaN(diffDays) || diffDays < 0) return 'Recently'
  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays} days ago`
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`
  return `${Math.floor(diffDays / 30)} months ago`
}

// ============================================
// Level 2: Teachings Card View
// ============================================

function TeachingsCardView({ goalData, onTeachingClick, onBack }: any) {
  if (!goalData) {
    return <div className="loading">Loading teachings...</div>
  }

  const { goal, sessions, curriculum, temporal_data } = goalData

  // Debug: log what we received
  console.log('[TeachingsCardView] Data received:', { 
    hasGoal: !!goal,
    sessionsCount: sessions?.length || 0, 
    curriculumCount: curriculum?.length || 0,
    curriculumType: Array.isArray(curriculum) ? 'array' : typeof curriculum,
    curriculumSample: curriculum ? (Array.isArray(curriculum) ? curriculum[0] : curriculum) : null
  })

  // Show curriculum if available, even if no teaching sessions yet
  if ((!sessions || sessions.length === 0) && (!curriculum || (Array.isArray(curriculum) && curriculum.length === 0))) {
    return (
      <div className="teachings-view">
        <div className="view-header">
          <button className="back-button" onClick={onBack}>← Back to Goals</button>
          <h2 className="view-title">{goal?.goal_text || 'Goal'}</h2>
        </div>
        <div className="profile-card empty-state">
          <p>No teaching sessions yet for this goal.</p>
        </div>
      </div>
    )
  }

  // Debug: log what we received
  console.log('[TeachingsCardView] Data:', { 
    sessions: sessions?.length || 0, 
    curriculum: curriculum?.length || 0,
    curriculumSample: curriculum?.[0] // Show first task structure
  })

  // Always prioritize curriculum tasks if available (they have proper names, descriptions, status)
  // Only fall back to sessions if no curriculum exists
  let displayItems: any[] = []
  const isShowingCurriculum = curriculum && curriculum.length > 0
  
  if (isShowingCurriculum) {
    // Sort curriculum tasks by id to maintain original proposal order
    displayItems = [...curriculum].sort((a: any, b: any) => {
      // Sort by id if available, otherwise by original index
      const aId = a.id !== undefined ? a.id : (a.index !== undefined ? a.index : 0)
      const bId = b.id !== undefined ? b.id : (b.index !== undefined ? b.index : 0)
      return aId - bId
    })
  } else if (sessions && sessions.length > 0) {
    // Fallback to sessions if no curriculum
    displayItems = sessions
  }

  return (
    <div className="teachings-view">
      <div className="view-header">
        <button className="back-button" onClick={onBack}>← Back to Goals</button>
        <h2 className="view-title">{goal?.goal_text || 'Goal'}</h2>
      </div>

      <div className="teachings-grid">
        {displayItems.map((item: any, idx: number) => {
          // For curriculum tasks (always show these if available)
          if (isShowingCurriculum) {
            const task = item
            // Determine status: check if there's a matching session for this task
            let status = task.status
            if (!status) {
              // Check if there's a session for this task topic
              const matchingSession = sessions?.find((s: any) => 
                s.schema_state?.topic === task.topic || 
                s.schema_state?.teaching_candidate?.topic === task.topic
              )
              if (matchingSession) {
                status = matchingSession.status || 'in-progress'
              } else {
                // Default: first task available, rest locked
                status = idx === 0 ? 'available' : 'locked'
              }
            }
            
            const isLocked = status === 'locked'
            const isCompleted = status === 'completed'
            const isInProgress = status === 'in_progress' || status === 'in-progress'
            const isAvailable = status === 'available'

            // Get description from task data
            const description = task.justification || task.identified_gap || task.focus_question || 'Ready to explore this topic'

            return (
              <div
                key={task.id || idx}
                className={`teaching-card profile-card ${isLocked ? 'locked' : 'clickable'}`}
                onClick={() => !isLocked && onTeachingClick(task.id || idx)}
              >
                <div className="card-header">
                  <span className="card-title">
                    {task.topic || task.title || `Topic ${idx + 1}`}
                  </span>
                  <span className={`readiness-badge ${status}`}>
                    {isLocked ? '🔒 Locked' : 
                     isCompleted ? '✓ Completed' : 
                     isInProgress ? '▶ In Progress' : 
                     isAvailable ? `${idx + 1}` : 
                     status || 'available'}
                  </span>
                </div>

                <div className="teaching-summary">
                  <p>{description}</p>
                </div>

                {isInProgress && (
                  <div className="teaching-progress-indicator">
                    <div className="progress-dot"></div>
                    <span>Active</span>
                  </div>
                )}
              </div>
            )
          }

          // For teaching sessions
          const session = item
          const sessionCheckpoints = temporal_data?.filter(
            (d: any) => d.session_id === session.session_id
          ) || []
          const latestCheckpoint = sessionCheckpoints[sessionCheckpoints.length - 1]

          return (
            <div
              key={session.session_id}
              className="teaching-card profile-card clickable"
              onClick={() => onTeachingClick(session.session_id)}
            >
              <div className="card-header">
                <span className="card-title">
                  {session.schema_state?.topic || session.schema_state?.teaching_candidate?.topic || 'Teaching Session'}
                </span>
                <span className={`readiness-badge ${session.status || 'active'}`}>
                  {session.status || 'in-progress'}
                </span>
              </div>

              <div className="teaching-summary">
                <p>{session.schema_state?.teaching_candidate?.identified_gap || session.schema_state?.teaching_candidate?.focus_question || 'Exploring concepts in depth'}</p>
              </div>

              {latestCheckpoint && (
                <>
                  <div className="teaching-progress-metrics">
                    <div className="mini-metric">
                      <span className="mini-label">Foundation</span>
                      <span className="mini-value">
                        {Math.round(latestCheckpoint.foundational_understanding * 100)}%
                      </span>
                    </div>
                    <div className="mini-metric">
                      <span className="mini-label">Applied</span>
                      <span className="mini-value">
                        {Math.round(latestCheckpoint.applied_mastery * 100)}%
                      </span>
                    </div>
                    <div className="mini-metric">
                      <span className="mini-label">Awareness</span>
                      <span className="mini-value">
                        {Math.round(latestCheckpoint.metacognitive_awareness * 100)}%
                      </span>
                    </div>
                  </div>

                  <div className="teaching-steps-progress">
                    <span className="steps-label">Steps</span>
                    <span className="steps-value">
                      {latestCheckpoint.teaching_steps_completed || 0} /{' '}
                      {latestCheckpoint.teaching_steps_total || 0}
                    </span>
                  </div>
                </>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ============================================
// Level 3: Teaching Detail View
// ============================================

function TeachingDetailView({ detailData, onBack }: any) {
  if (!detailData) {
    return <div className="loading">Loading detail...</div>
  }

  const { session, understanding_timeline, current_aggregates, curriculum_plan } = detailData

  // Format timeline data for Recharts
  const chartData = understanding_timeline?.map((point: any) => ({
    turn: point.turn,
    Foundation: Math.round(point.foundational_understanding * 100),
    Applied: Math.round(point.applied_mastery * 100),
    Awareness: Math.round(point.metacognitive_awareness * 100)
  })) || []

  return (
    <div className="teaching-detail-view">
      <div className="view-header">
        <button className="back-button" onClick={onBack}>← Back to Teachings</button>
        <h2 className="view-title">
          {session?.schema_state?.topic || 'Teaching Session'}
        </h2>
      </div>

      {/* Current State Summary */}
      <div className="profile-card">
        <div className="card-header">
          <span className="card-title">Current Understanding</span>
        </div>
        <div className="current-metrics-grid">
          <div className="metric-box">
            <div className="metric-label">Foundational Understanding</div>
            <div className="metric-value-large">
              {Math.round((current_aggregates?.foundational_understanding || 0) * 100)}%
            </div>
            <div className="metric-description">Do I understand the basics?</div>
          </div>
          <div className="metric-box">
            <div className="metric-label">Applied Mastery</div>
            <div className="metric-value-large">
              {Math.round((current_aggregates?.applied_mastery || 0) * 100)}%
            </div>
            <div className="metric-description">Can I actually use this?</div>
          </div>
          <div className="metric-box">
            <div className="metric-label">Metacognitive Awareness</div>
            <div className="metric-value-large">
              {Math.round((current_aggregates?.metacognitive_awareness || 0) * 100)}%
            </div>
            <div className="metric-description">Do I know what I know?</div>
          </div>
        </div>
      </div>

      {/* Progress Over Time Chart */}
      {chartData.length > 0 && (
        <div className="profile-card">
          <div className="card-header">
            <span className="card-title">Understanding Development</span>
          </div>
          <div className="chart-section">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis
                  dataKey="turn"
                  label={{ value: 'Conversation Turn', position: 'insideBottom', offset: -5 }}
                />
                <YAxis
                  label={{ value: 'Understanding (%)', angle: -90, position: 'insideLeft' }}
                  domain={[0, 100]}
                />
                <Tooltip />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="Foundation"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  dot={{ r: 4 }}
                />
                <Line
                  type="monotone"
                  dataKey="Applied"
                  stroke="#10b981"
                  strokeWidth={2}
                  dot={{ r: 4 }}
                />
                <Line
                  type="monotone"
                  dataKey="Awareness"
                  stroke="#f59e0b"
                  strokeWidth={2}
                  dot={{ r: 4 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Curriculum Steps */}
      {curriculum_plan?.steps && curriculum_plan.steps.length > 0 && (
        <div className="profile-card">
          <div className="card-header">
            <span className="card-title">Project Path</span>
          </div>
          <div className="curriculum-steps">
            {curriculum_plan.steps.map((step: any, idx: number) => (
              <div key={idx} className={`curriculum-step ${step.status || ''}`}>
                <div className="step-number">{idx + 1}</div>
                <div className="step-content">
                  <div className="step-objective">{step.objective}</div>
                  {step.status === 'completed' && (
                    <div className="step-meta">✓ Completed</div>
                  )}
                  {step.status === 'in_progress' && (
                    <div className="step-meta">→ Currently working on this</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
