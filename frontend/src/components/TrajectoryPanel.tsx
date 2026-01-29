import { useCallback, useEffect, useState } from 'react'
import { api, LearnerTrajectoryDashboard, UserData } from '../services/api'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  AreaChart, Area,
} from 'recharts'

interface TrajectoryPanelProps {
  userId: string
}

export default function TrajectoryPanel({ userId }: TrajectoryPanelProps) {
  const [data, setData] = useState<LearnerTrajectoryDashboard | null>(null)
  const [userData, setUserData] = useState<UserData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Modal state for goal drill-down
  const [modalGoalId, setModalGoalId] = useState<number | null>(null)
  const [goalProgressData, setGoalProgressData] = useState<any>(null)
  const [teachingDetailData, setTeachingDetailData] = useState<any>(null)
  const [modalView, setModalView] = useState<'teachings' | 'detail'>('teachings')
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [_selectedTeachingId, setSelectedTeachingId] = useState<string | null>(null)

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

      if (d && (!d.goals || d.goals.length === 0)) {
        try {
          const refreshed = await api.refreshTrajectory(userId)
          setData(refreshed)
        } catch (refreshError) {
          console.error('[Trajectory] Auto-refresh failed:', refreshError)
        }
      }
    } catch (e: any) {
      setError(e?.message || 'Failed to load dashboard')
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

  useEffect(() => { load() }, [load])

  // Modal: fetch goal progress when opening
  const openGoalModal = useCallback(async (goalId: number) => {
    setModalGoalId(goalId)
    setModalView('teachings')
    setSelectedTeachingId(null)
    setTeachingDetailData(null)
    try {
      const response = await fetch(`/api/goal/${goalId}/progress?user_id=${userId}`)
      const d = await response.json()
      setGoalProgressData(d)
    } catch (e) {
      console.error('Failed to fetch goal progress:', e)
    }
  }, [userId])

  const openTeachingDetail = useCallback(async (sessionId: string) => {
    setSelectedTeachingId(sessionId)
    setModalView('detail')
    try {
      const response = await fetch(`/api/teaching/${sessionId}/detail?user_id=${userId}`)
      const d = await response.json()
      setTeachingDetailData(d)
    } catch (e) {
      console.error('Failed to fetch teaching detail:', e)
    }
  }, [userId])

  const closeModal = () => {
    setModalGoalId(null)
    setGoalProgressData(null)
    setTeachingDetailData(null)
    setSelectedTeachingId(null)
  }

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
        <div className="loading">Loading dashboard...</div>
      </div>
    )
  }

  const updated_at = data?.updated_at

  return (
    <div className="trajectory-panel">
      <div className="trajectory-panel-header">
        <h1 className="panel-title">Your Project Mind</h1>
        {updated_at && (
          <span className="last-updated-badge">
            Updated {new Date(updated_at).toLocaleString()}
          </span>
        )}
        <button onClick={refresh} className="refresh-button">Refresh</button>
      </div>

      <div className="trajectory-panel-content">
        <div className="trajectory-dashboard">
          <InsightsBanner data={data} />

          <div className="trajectory-two-col">
            <ProjectIdentityCard userData={userData} learnerModel={data?.learner_model} />
            <GoalsMomentumPanel goals={data?.goals || []} onGoalClick={openGoalModal} />
          </div>

          {data?.highlights && data.highlights.length > 0 && (
            <HighlightsTimeline highlights={data.highlights} />
          )}

          <ProfileEvolutionChart learnerModel={data?.learner_model} />
        </div>
      </div>

      {/* Goal drill-down modal */}
      {modalGoalId !== null && (
        <GoalDrillDownModal
          goalProgressData={goalProgressData}
          teachingDetailData={teachingDetailData}
          modalView={modalView}
          onTeachingClick={openTeachingDetail}
          onBackToTeachings={() => { setModalView('teachings'); setTeachingDetailData(null); setSelectedTeachingId(null) }}
          onClose={closeModal}
        />
      )}
    </div>
  )
}

// ============================================
// Insights Banner
// ============================================

function InsightsBanner({ data }: { data: LearnerTrajectoryDashboard | null }) {
  const insights = data?.insights
  const sessionsPerWeek = data?.engagement?.sessions_per_week || []

  const sparklineData = sessionsPerWeek.map((v: number, i: number) => ({ week: i + 1, sessions: v }))

  return (
    <div className="trajectory-hero">
      <div className="hero-text">
        <h3>Insights</h3>
        <p>{insights && insights.trim() ? insights : 'Keep exploring — patterns will emerge as you make progress.'}</p>
      </div>
      {sparklineData.length > 1 && (
        <div className="hero-sparkline">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={sparklineData}>
              <Area type="monotone" dataKey="sessions" stroke="#6366f1" fill="#c7d2fe" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

// ============================================
// Project Identity Card (radar + traits)
// ============================================

/** Grab the latest value from a learner_model field (which is an array of snapshots over time). */
const latest = (arr: any) => {
  if (Array.isArray(arr) && arr.length > 0) return arr[arr.length - 1]
  return arr  // already a single value or null
}

function ProjectIdentityCard({ userData, learnerModel }: { userData: UserData | null; learnerModel: any }) {
  const entryMode = latest(learnerModel?.entry_mode) || (userData as any)?.entry_mode
  const curiosityType = latest(learnerModel?.curiosity_type) || (userData as any)?.curiosity_type
  const motivationProfile = latest(learnerModel?.motivation_profile) || (userData as any)?.motivation_profile
  const pacingPref = latest(learnerModel?.pacing_preference) || (userData as any)?.pacing_preference
  const uncertaintyTol = latest(learnerModel?.uncertainty_tolerance) || (userData as any)?.uncertainty_tolerance

  const hasData = entryMode || curiosityType || motivationProfile

  // Build radar data from entry_mode dimensions
  const radarData: { dimension: string; value: number }[] = []
  if (entryMode && typeof entryMode === 'object') {
    Object.entries(entryMode).forEach(([key, val]) => {
      if (typeof val === 'number') {
        radarData.push({ dimension: key.replace(/_/g, ' '), value: val })
      } else if (val && typeof val === 'object' && (val as any).value !== undefined) {
        radarData.push({ dimension: key.replace(/_/g, ' '), value: Number((val as any).value) || 0 })
      }
    })
  }

  // Motivation micro-bars
  const motivationBars: { label: string; value: number }[] = []
  if (motivationProfile && typeof motivationProfile === 'object') {
    Object.entries(motivationProfile).forEach(([key, val]) => {
      if (typeof val === 'number') {
        motivationBars.push({ label: key.replace(/_/g, ' '), value: val })
      } else if (val && typeof val === 'object' && (val as any).value !== undefined) {
        motivationBars.push({ label: key.replace(/_/g, ' '), value: Number((val as any).value) || 0 })
      }
    })
  }

  const traits: string[] = []
  if (curiosityType) {
    const cv = typeof curiosityType === 'object' ? curiosityType.value : curiosityType
    if (cv) traits.push(String(cv))
  }
  if (pacingPref) {
    const pv = typeof pacingPref === 'object' ? pacingPref.value : pacingPref
    if (pv) traits.push(String(pv))
  }
  if (uncertaintyTol) {
    const uv = typeof uncertaintyTol === 'object' ? uncertaintyTol.value : uncertaintyTol
    if (uv) traits.push(String(uv))
  }

  return (
    <div className="trajectory-identity-card">
      <h3>Your Working Style</h3>
      {!hasData ? (
        <div className="identity-placeholder">
          Start a conversation to discover your working style.
        </div>
      ) : (
        <>
          {radarData.length >= 3 && (
            <ResponsiveContainer width="100%" height={200}>
              <RadarChart data={radarData}>
                <PolarGrid stroke="#e2e8f0" />
                <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 11, fill: '#64748b' }} />
                <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} />
                <Radar dataKey="value" stroke="#6366f1" fill="#c7d2fe" fillOpacity={0.5} />
              </RadarChart>
            </ResponsiveContainer>
          )}
          {traits.length > 0 && (
            <div className="identity-traits">
              {traits.map((t, i) => <span key={i} className="identity-trait">{t}</span>)}
            </div>
          )}
          {motivationBars.length > 0 && (
            <div className="micro-bars-group">
              {motivationBars.map((m, i) => (
                <div key={i} className="micro-bar-row">
                  <span className="micro-bar-label">{m.label}</span>
                  <div className="micro-bar">
                    <div className="micro-bar-fill" style={{ width: `${Math.round(m.value * 100)}%` }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ============================================
// Goals Momentum Panel
// ============================================

function GoalsMomentumPanel({ goals, onGoalClick }: { goals: any[]; onGoalClick: (id: number) => void }) {
  if (!goals || goals.length === 0) {
    return (
      <div className="trajectory-goals-panel">
        <h3>Goals</h3>
        <div className="identity-placeholder">
          Start a conversation to set your first project goal.
        </div>
      </div>
    )
  }

  return (
    <div className="trajectory-goals-panel">
      <h3>Goals</h3>
      {goals.map((goal: any) => {
        const momentum = goal.momentum || 'active'
        const dotClass = momentum === 'moving' ? 'moving' : momentum === 'stuck' ? 'stuck' : momentum === 'inactive' ? 'inactive' : ''
        return (
          <div
            key={goal.goal_id}
            className="goal-momentum-card"
            onClick={() => onGoalClick(goal.goal_id)}
          >
            <div className={`momentum-dot ${dotClass}`} />
            <div className="goal-momentum-info">
              <p className="goal-title">{goal.goal_text}</p>
              <p className="goal-summary">
                {goal.learning_summary || goal.next_suggested_move || 'Ready to dive in'}
              </p>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ============================================
// Highlights Timeline
// ============================================

function HighlightsTimeline({ highlights }: { highlights: any[] }) {
  return (
    <div>
      <h3 style={{ fontSize: 14, fontWeight: 600, color: '#334155', margin: '0 0 12px 0' }}>Highlights</h3>
      <div className="trajectory-highlights-timeline">
        {highlights.map((h: any, i: number) => {
          const kindClass = h.kind ? `kind-${h.kind}` : ''
          return (
            <div key={h.id || i} className={`highlight-card ${kindClass}`}>
              <p className="highlight-kind">{(h.kind || 'note').replace(/_/g, ' ')}</p>
              <p className="highlight-summary">{h.summary}</p>
              {h.evidence_quote && <p className="highlight-quote">"{h.evidence_quote}"</p>}
              <div className="highlight-confidence">
                Confidence: {Math.round((h.confidence || 0) * 100)}%
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ============================================
// Profile Evolution Chart
// ============================================

function ProfileEvolutionChart({ learnerModel }: { learnerModel: any }) {
  // Derive profile confidence from trait confidence values across checkpoints
  // Each trait (pacing_preference, uncertainty_tolerance, curiosity_type) is an array of snapshots with confidence
  const pacingArr = learnerModel?.pacing_preference || []
  const uncertaintyArr = learnerModel?.uncertainty_tolerance || []
  const curiosityArr = learnerModel?.curiosity_type || []
  const entryModeArr = learnerModel?.entry_mode || []
  const motivationArr = learnerModel?.motivation_profile || []

  // Find the max number of checkpoints across all traits
  const traitArrays = [pacingArr, uncertaintyArr, curiosityArr, entryModeArr, motivationArr]
  const maxCheckpoints = Math.max(...traitArrays.map((a: any[]) => Array.isArray(a) ? a.length : 0))

  if (maxCheckpoints < 2) return null

  // For each checkpoint, compute average confidence across available traits
  const getConfidence = (item: any): number | null => {
    if (!item) return null
    if (typeof item === 'object' && item.confidence !== undefined) return Number(item.confidence)
    return null
  }

  // Compute a "trait richness" score: how many dimensions are populated at each checkpoint
  const chartData = Array.from({ length: maxCheckpoints }, (_, i) => {
    const confidences: number[] = []
    for (const arr of traitArrays) {
      if (Array.isArray(arr) && arr[i]) {
        const c = getConfidence(arr[i])
        if (c !== null) confidences.push(c)
      }
    }
    const avgConfidence = confidences.length > 0
      ? confidences.reduce((a, b) => a + b, 0) / confidences.length
      : null
    const traitCoverage = traitArrays.filter((a: any[]) => Array.isArray(a) && a.length > i).length / traitArrays.length

    return {
      point: i + 1,
      profile: avgConfidence !== null ? Math.round(avgConfidence * 100) : null,
      coverage: Math.round(traitCoverage * 100),
    }
  })

  const hasNonZero = chartData.some(d => (d.profile !== null && d.profile > 0) || d.coverage > 0)
  if (!hasNonZero) return null

  return (
    <div className="trajectory-evolution-chart">
      <h3>Profile Evolution</h3>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="point" label={{ value: 'Checkpoint', position: 'insideBottom', offset: -5, fontSize: 11 }} tick={{ fontSize: 11 }} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend />
          <Area type="monotone" dataKey="profile" name="Trait Confidence" stroke="#6366f1" fill="#c7d2fe" fillOpacity={0.4} connectNulls />
          <Area type="monotone" dataKey="coverage" name="Profile Coverage" stroke="#10b981" fill="#a7f3d0" fillOpacity={0.4} connectNulls />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

// ============================================
// Goal Drill-Down Modal
// ============================================

function GoalDrillDownModal({
  goalProgressData, teachingDetailData, modalView,
  onTeachingClick, onBackToTeachings, onClose,
}: {
  goalProgressData: any
  teachingDetailData: any
  modalView: 'teachings' | 'detail'
  onTeachingClick: (id: string) => void
  onBackToTeachings: () => void
  onClose: () => void
}) {
  return (
    <div className="trajectory-modal-overlay" onClick={onClose}>
      <div className="trajectory-modal-content" onClick={e => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>&times;</button>
        {modalView === 'teachings' ? (
          <TeachingsCardView
            goalData={goalProgressData}
            onTeachingClick={onTeachingClick}
          />
        ) : (
          <TeachingDetailView
            detailData={teachingDetailData}
            onBack={onBackToTeachings}
          />
        )}
      </div>
    </div>
  )
}

// ============================================
// Teachings Card View (preserved from original)
// ============================================

function TeachingsCardView({ goalData, onTeachingClick }: any) {
  if (!goalData) {
    return <div className="loading">Loading teachings...</div>
  }

  const { goal, sessions, curriculum, temporal_data } = goalData

  if ((!sessions || sessions.length === 0) && (!curriculum || (Array.isArray(curriculum) && curriculum.length === 0))) {
    return (
      <div className="teachings-view">
        <div className="view-header">
          <h2 className="view-title">{goal?.goal_text || 'Goal'}</h2>
        </div>
        <div className="profile-card empty-state">
          <p>No teaching sessions yet for this goal.</p>
        </div>
      </div>
    )
  }

  let displayItems: any[] = []
  const isShowingCurriculum = curriculum && curriculum.length > 0

  if (isShowingCurriculum) {
    displayItems = [...curriculum].sort((a: any, b: any) => {
      const aId = a.id !== undefined ? a.id : 0
      const bId = b.id !== undefined ? b.id : 0
      return aId - bId
    })
  } else if (sessions && sessions.length > 0) {
    displayItems = sessions
  }

  return (
    <div className="teachings-view">
      <div className="view-header">
        <h2 className="view-title">{goal?.goal_text || 'Goal'}</h2>
      </div>

      <div className="teachings-grid">
        {displayItems.map((item: any, idx: number) => {
          if (isShowingCurriculum) {
            const task = item
            let status = task.status
            if (!status) {
              const matchingSession = sessions?.find((s: any) =>
                s.schema_state?.topic === task.topic ||
                s.schema_state?.teaching_candidate?.topic === task.topic
              )
              if (matchingSession) {
                status = matchingSession.status || 'in-progress'
              } else {
                status = idx === 0 ? 'available' : 'locked'
              }
            }

            const isLocked = status === 'locked'
            const isCompleted = status === 'completed'
            const isInProgress = status === 'in_progress' || status === 'in-progress'
            const description = task.justification || task.identified_gap || task.focus_question || 'Ready to explore this topic'

            return (
              <div
                key={task.id || idx}
                className={`teaching-card profile-card ${isLocked ? 'locked' : 'clickable'}`}
                onClick={() => !isLocked && onTeachingClick(task.id || idx)}
              >
                <div className="card-header">
                  <span className="card-title">{task.topic || task.title || `Topic ${idx + 1}`}</span>
                  <span className={`readiness-badge ${status}`}>
                    {isLocked ? 'Locked' : isCompleted ? 'Completed' : isInProgress ? 'In Progress' : status || 'available'}
                  </span>
                </div>
                <div className="teaching-summary"><p>{description}</p></div>
                {isInProgress && (
                  <div className="teaching-progress-indicator">
                    <div className="progress-dot"></div>
                    <span>Active</span>
                  </div>
                )}
              </div>
            )
          }

          const session = item
          const sessionCheckpoints = temporal_data?.filter((d: any) => d.session_id === session.session_id) || []
          const latestCheckpoint = sessionCheckpoints[sessionCheckpoints.length - 1]

          return (
            <div
              key={session.session_id}
              className="teaching-card profile-card clickable"
              onClick={() => onTeachingClick(session.session_id)}
            >
              <div className="card-header">
                <span className="card-title">
                  {session.schema_state?.topic || session.schema_state?.teaching_candidate?.topic || 'Session'}
                </span>
                <span className={`readiness-badge ${session.status || 'active'}`}>
                  {session.status || 'in-progress'}
                </span>
              </div>
              <div className="teaching-summary">
                <p>{session.schema_state?.teaching_candidate?.identified_gap || session.schema_state?.teaching_candidate?.focus_question || 'Exploring concepts'}</p>
              </div>
              {latestCheckpoint && (
                <>
                  <div className="teaching-progress-metrics">
                    <div className="mini-metric">
                      <span className="mini-label">Foundation</span>
                      <span className="mini-value">{Math.round(latestCheckpoint.foundational_understanding * 100)}%</span>
                    </div>
                    <div className="mini-metric">
                      <span className="mini-label">Applied</span>
                      <span className="mini-value">{Math.round(latestCheckpoint.applied_mastery * 100)}%</span>
                    </div>
                    <div className="mini-metric">
                      <span className="mini-label">Awareness</span>
                      <span className="mini-value">{Math.round(latestCheckpoint.metacognitive_awareness * 100)}%</span>
                    </div>
                  </div>
                  <div className="teaching-steps-progress">
                    <span className="steps-label">Steps</span>
                    <span className="steps-value">{latestCheckpoint.teaching_steps_completed || 0} / {latestCheckpoint.teaching_steps_total || 0}</span>
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
// Teaching Detail View (preserved from original)
// ============================================

function TeachingDetailView({ detailData, onBack }: any) {
  if (!detailData) {
    return <div className="loading">Loading detail...</div>
  }

  const { session, understanding_timeline, current_aggregates, curriculum_plan } = detailData

  const chartData = understanding_timeline?.map((point: any) => ({
    turn: point.turn,
    Foundation: Math.round(point.foundational_understanding * 100),
    Applied: Math.round(point.applied_mastery * 100),
    Awareness: Math.round(point.metacognitive_awareness * 100),
  })) || []

  return (
    <div className="teaching-detail-view">
      <div className="view-header">
        <button className="back-button" onClick={onBack}>← Back</button>
        <h2 className="view-title">{session?.schema_state?.topic || 'Session'}</h2>
      </div>

      <div className="profile-card">
        <div className="card-header"><span className="card-title">Summary</span></div>
        <div className="current-metrics-grid">
          <div className="metric-box">
            <div className="metric-label">Foundational Understanding</div>
            <div className="metric-value-large">{Math.round((current_aggregates?.foundational_understanding || 0) * 100)}%</div>
          </div>
          <div className="metric-box">
            <div className="metric-label">Applied Mastery</div>
            <div className="metric-value-large">{Math.round((current_aggregates?.applied_mastery || 0) * 100)}%</div>
          </div>
          <div className="metric-box">
            <div className="metric-label">Metacognitive Awareness</div>
            <div className="metric-value-large">{Math.round((current_aggregates?.metacognitive_awareness || 0) * 100)}%</div>
          </div>
        </div>
      </div>

      {chartData.length > 0 && (
        <div className="profile-card">
          <div className="card-header"><span className="card-title">Understanding Development</span></div>
          <div className="chart-section">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="turn" label={{ value: 'Turn', position: 'insideBottom', offset: -5 }} />
                <YAxis label={{ value: 'Understanding (%)', angle: -90, position: 'insideLeft' }} domain={[0, 100]} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="Foundation" stroke="#3b82f6" strokeWidth={2} dot={{ r: 4 }} />
                <Line type="monotone" dataKey="Applied" stroke="#10b981" strokeWidth={2} dot={{ r: 4 }} />
                <Line type="monotone" dataKey="Awareness" stroke="#f59e0b" strokeWidth={2} dot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {curriculum_plan?.steps && curriculum_plan.steps.length > 0 && (
        <div className="profile-card">
          <div className="card-header"><span className="card-title">Project Path</span></div>
          <div className="curriculum-steps">
            {curriculum_plan.steps.map((step: any, idx: number) => (
              <div key={idx} className={`curriculum-step ${step.status || ''}`}>
                <div className="step-number">{idx + 1}</div>
                <div className="step-content">
                  <div className="step-objective">{step.objective}</div>
                  {step.status === 'completed' && <div className="step-meta">Completed</div>}
                  {step.status === 'in_progress' && <div className="step-meta">Currently working on this</div>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
