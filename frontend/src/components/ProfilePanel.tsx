import { useState, useEffect, useCallback } from 'react'
import { api, TeachingSchema, UnderstandingMarker } from '../services/api'

interface ProfilePanelProps {
  sessionId: string | null
  isConnected: boolean
  initialSummary?: string
  isTeachingSession?: boolean
  onGoalSelected?: (goalText: string) => void
}

// Helper functions to convert numeric values to descriptive labels

const getReadinessLabel = (score: number | undefined): { label: string; level: string } => {
  if (score === undefined || score === null) return { label: 'Unknown', level: 'unknown' }
  if (score >= 0.7) return { label: 'Ready', level: 'high' }
  if (score >= 0.5) return { label: 'Developing', level: 'medium' }
  return { label: 'Emerging', level: 'low' }
}

const getDominantEntryMode = (entryMode: any): { mode: string; icon: string } => {
  if (!entryMode) return { mode: 'Exploring', icon: '🔍' }
  const { people = 0, problems = 0, ideas = 0 } = entryMode
  const max = Math.max(people, problems, ideas)
  if (max < 0.3) return { mode: 'Exploring', icon: '🔍' }
  if (people === max) return { mode: 'People-oriented', icon: '👥' }
  if (problems === max) return { mode: 'Problem-solver', icon: '🎯' }
  return { mode: 'Ideas-driven', icon: '💡' }
}

const getConfidenceLabel = (confidence: number | undefined): string => {
  if (confidence === undefined || confidence === null) return ''
  if (confidence >= 0.7) return 'Strong signal'
  if (confidence >= 0.4) return 'Moderate signal'
  return 'Weak signal'
}

const formatTraitValue = (trait: any): { value: string; confidence: string } => {
  if (!trait) return { value: '—', confidence: '' }
  
  if (typeof trait === 'object') {
    if ('value' in trait) {
      return { 
        value: trait.value || '—', 
        confidence: getConfidenceLabel(trait.confidence) 
      }
    }
    return { value: '—', confidence: '' }
  }
  
  return { value: String(trait), confidence: '' }
}

// Understanding marker level badge helper
const getMarkerLevelBadge = (level: string): { label: string; className: string } => {
  switch (level) {
    case 'strong':
      return { label: 'Strong', className: 'marker-strong' }
    case 'developing':
      return { label: 'Developing', className: 'marker-developing' }
    default:
      return { label: 'Not Yet', className: 'marker-not-yet' }
  }
}

export default function ProfilePanel({ sessionId, isConnected, initialSummary, isTeachingSession = false, onGoalSelected }: ProfilePanelProps) {
  const [schema, setSchema] = useState<any>(null)
  const [teachingSchema, setTeachingSchema] = useState<TeachingSchema | null>(null)
  const [summary, setSummary] = useState<string>(initialSummary || '')
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false)
  const [lastSummaryTurn, setLastSummaryTurn] = useState(initialSummary ? 0 : -1)

  useEffect(() => {
    if (initialSummary) {
      setSummary(initialSummary)
      setLastSummaryTurn(0)
    }
  }, [initialSummary])

  useEffect(() => {
    if (!sessionId || !isConnected) return

    const fetchSchema = async () => {
      try {
        if (isTeachingSession) {
          // Fetch teaching state
          const data = await api.getTeachingState(sessionId)
          setTeachingSchema(data)
          // Use narrative_summary from teaching schema
          if (data.narrative_summary) {
            setSummary(data.narrative_summary)
          }
        } else {
          // Fetch discovery schema
          const data = await api.getDiscoverySchema(sessionId)
          setSchema(data)
        }
      } catch (error) {
        console.error('Failed to fetch schema:', error)
      }
    }

    fetchSchema()
    const interval = setInterval(fetchSchema, 3000)
    return () => clearInterval(interval)
  }, [sessionId, isConnected, isTeachingSession])

  const generateSummary = useCallback(async (forceRefresh = false) => {
    if (isTeachingSession) {
      // For teaching sessions, we use the narrative_summary from the schema
      return
    }
    
    if (!schema || !sessionId || isGeneratingSummary) return
    
    const currentTurn = schema.interview_state?.turns_elapsed || 0
    // Only skip if not forcing refresh and summary exists and not enough turns
    if (!forceRefresh && summary && currentTurn - lastSummaryTurn < 2) return
    
    setIsGeneratingSummary(true)
    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      const response = await fetch(`${apiUrl}/api/profile/summary`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ schema })
      })
      if (response.ok) {
        const data = await response.json()
        setSummary(data.summary)
        setLastSummaryTurn(currentTurn)
        try {
          await api.saveProfileSummary(sessionId, data.summary)
        } catch (saveErr) {
          console.error('Failed to save summary:', saveErr)
        }
      }
    } catch (err) {
      console.error('Failed to generate summary:', err)
    } finally {
      setIsGeneratingSummary(false)
    }
  }, [schema, sessionId, summary, lastSummaryTurn, isGeneratingSummary, isTeachingSession])

  // Auto-generate summary on first load and every 2 turns
  useEffect(() => {
    if (schema && !isTeachingSession) {
      const currentTurn = schema.interview_state?.turns_elapsed || 0
      // Generate if no summary OR if enough turns have passed
      if (!summary || currentTurn - lastSummaryTurn >= 2) {
        generateSummary()
      }
    }
  }, [schema, isTeachingSession]) // Intentionally exclude summary and lastSummaryTurn to allow re-generation

  // Render teaching session panel
  if (isTeachingSession) {
    if (!teachingSchema) {
      return (
        <div className="profile-panel">
          <div className="profile-panel-header">
            <h2>Learning Progress</h2>
          </div>
          <div className="profile-panel-content">
            <div className="profile-card empty-state">
              <p>Loading teaching session...</p>
            </div>
          </div>
        </div>
      )
    }

    const curriculum = teachingSchema.curriculum_plan
    const markers = teachingSchema.understanding_markers || []
    const activeMarkers = markers.filter((m: UnderstandingMarker) => m.level !== 'not_yet')
    const currentStep = curriculum?.steps?.[teachingSchema.current_step_index]

    return (
      <div className="profile-panel">
        <div className="profile-panel-header">
          <h2>Learning Progress</h2>
          <span className="turn-counter">Turn {teachingSchema.turns_elapsed || 0}</span>
        </div>

        <div className="profile-panel-content">
          {/* Narrative Summary */}
          <div className="profile-card summary-card">
            <div className="card-header">
              <span className="card-title">Understanding</span>
            </div>
            <p className="summary-text">
              {teachingSchema.narrative_summary || 'Building understanding...'}
            </p>
          </div>

          {/* Curriculum Progress */}
          {curriculum && curriculum.steps && curriculum.steps.length > 0 && (
            <div className="profile-card">
              <div className="card-header">
                <span className="card-title">Learning Path</span>
                <span className="item-count">
                  {curriculum.completed_step_ids?.length || 0}/{curriculum.steps.length}
                </span>
              </div>
              <div className="curriculum-steps">
                {curriculum.steps.map((step, idx) => {
                  const isCompleted = curriculum.completed_step_ids?.includes(step.id)
                  const isCurrent = idx === teachingSchema.current_step_index
                  return (
                    <div 
                      key={step.id} 
                      className={`curriculum-step ${isCompleted ? 'completed' : ''} ${isCurrent ? 'current' : ''}`}
                    >
                      <span className="step-number">{idx + 1}</span>
                      <span className="step-objective">{step.objective}</span>
                      {isCompleted && <span className="step-check">✓</span>}
                      {isCurrent && <span className="step-arrow">→</span>}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Current Step Details */}
          {currentStep && (
            <div className="profile-card focus-card">
              <div className="card-header">
                <span className="card-title">Current Focus</span>
              </div>
              <div className="focus-details">
                <p className="current-objective">{currentStep.objective}</p>
                <div className="focus-item">
                  <span className="focus-label">Approach</span>
                  <span className="focus-value">{currentStep.explanation_approach}</span>
                </div>
                {currentStep.marker_targets && currentStep.marker_targets.length > 0 && (
                  <div className="focus-item">
                    <span className="focus-label">Building</span>
                    <span className="focus-value">{currentStep.marker_targets.join(', ')}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Understanding Markers */}
          <div className="profile-card">
            <div className="card-header">
              <span className="card-title">Understanding Markers</span>
              <span className="item-count">{activeMarkers.length} active</span>
            </div>
            <div className="markers-grid">
              {markers.map((marker: UnderstandingMarker) => {
                const badge = getMarkerLevelBadge(marker.level)
                const hasEvidence = marker.evidence && marker.evidence.length > 0
                
                if (marker.level === 'not_yet' && !hasEvidence) {
                  return null // Hide markers with no activity
                }
                
                return (
                  <div key={marker.id} className={`marker-item ${badge.className}`}>
                    <div className="marker-header">
                      <span className="marker-name">{marker.name}</span>
                      <span className={`marker-badge ${badge.className}`}>{badge.label}</span>
                    </div>
                    {hasEvidence && (
                      <p className="marker-evidence">
                        "{marker.evidence[marker.evidence.length - 1]}"
                      </p>
                    )}
                  </div>
                )
              })}
              {activeMarkers.length === 0 && (
                <p className="markers-empty">Markers will appear as you demonstrate understanding.</p>
              )}
            </div>
          </div>

          {/* Open Questions */}
          {teachingSchema.open_questions && teachingSchema.open_questions.length > 0 && (
            <div className="profile-card">
              <div className="card-header">
                <span className="card-title">Open Questions</span>
              </div>
              <ul className="open-questions-list">
                {teachingSchema.open_questions.map((q, idx) => (
                  <li key={idx} className="open-question">{q}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Prerequisite Gaps */}
          {teachingSchema.prerequisite_gaps && teachingSchema.prerequisite_gaps.length > 0 && (
            <div className="profile-card warning-card">
              <div className="card-header">
                <span className="card-title">⚠️ Foundation Gaps</span>
              </div>
              <ul className="gaps-list">
                {teachingSchema.prerequisite_gaps.map((gap, idx) => (
                  <li key={idx} className="gap-item">{gap}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    )
  }

  // Render discovery session panel (existing code)
  if (!schema) {
    return (
      <div className="profile-panel">
        <div className="profile-panel-header">
          <h2>Learner Profile</h2>
        </div>
        <div className="profile-panel-content">
          <div className="profile-card empty-state">
            <p>Waiting for conversation data...</p>
          </div>
        </div>
      </div>
    )
  }

  const profile = schema.user_profile || {}
  const goalCandidates = schema.goal_candidates || []
  const teachingCandidates = schema.teaching_candidates || []
  const themes = schema.conversational_themes || []
  const interviewState = schema.interview_state || {}
  const controller = schema.controller || {}

  const entryMode = getDominantEntryMode(profile.entry_mode)
  const curiosity = formatTraitValue(profile.curiosity_type)
  const uncertainty = formatTraitValue(profile.uncertainty_tolerance)
  const pacing = formatTraitValue(profile.pacing_preference)
  const motivation = profile.motivation_profile?.primary_driver || '—'

  return (
    <div className="profile-panel">
      <div className="profile-panel-header">
        <h2>Learner Profile</h2>
        <span className="turn-counter">Turn {interviewState.turns_elapsed || 0}</span>
      </div>

      <div className="profile-panel-content">
        {/* Summary Card */}
        <div className="profile-card summary-card">
          <div className="card-header">
            <span className="card-title">Current Understanding</span>
            <button 
              className="refresh-btn"
              onClick={() => generateSummary(true)}
              disabled={isGeneratingSummary}
              title="Refresh summary"
            >
              {isGeneratingSummary ? '...' : '↻'}
            </button>
          </div>
          <p className="summary-text">
            {isGeneratingSummary && !summary 
              ? 'Analyzing conversation...' 
              : summary || 'Continue the conversation to build your learner profile.'}
          </p>
        </div>

        {/* Learning Style Traits */}
        <div className="profile-card">
          <div className="card-header">
            <span className="card-title">How You Learn</span>
          </div>
          <div className="trait-grid">
            <div className="trait-item">
              <span className="trait-icon">{entryMode.icon}</span>
              <span className="trait-label">Entry</span>
              <span className="trait-value">{entryMode.mode}</span>
            </div>
            <div className="trait-item">
              <span className="trait-icon">🔮</span>
              <span className="trait-label">Curiosity</span>
              <span className="trait-value">{curiosity.value}</span>
              {curiosity.confidence && <span className="trait-confidence">{curiosity.confidence}</span>}
            </div>
            <div className="trait-item">
              <span className="trait-icon">⚡</span>
              <span className="trait-label">Pacing</span>
              <span className="trait-value">{pacing.value}</span>
            </div>
            <div className="trait-item">
              <span className="trait-icon">🌊</span>
              <span className="trait-label">Uncertainty</span>
              <span className="trait-value">{uncertainty.value}</span>
            </div>
            <div className="trait-item">
              <span className="trait-icon">🔥</span>
              <span className="trait-label">Driver</span>
              <span className="trait-value">{motivation}</span>
            </div>
          </div>
        </div>

        {/* Goal Candidates */}
        {goalCandidates.length > 0 && (
          <div className="profile-card">
            <div className="card-header">
              <span className="card-title">Emerging Goals</span>
              <span className="item-count">{Math.min(goalCandidates.length, 5)}{goalCandidates.length > 5 ? '+' : ''}</span>
            </div>
            <div className="goal-list">
              {/* Sort by readiness score (descending) and limit to top 5 */}
              {[...goalCandidates]
                .map((goal: any) => ({
                  ...goal,
                  avgScore: (
                    (goal.concreteness || 0) + 
                    (goal.scope_appropriateness || 0) + 
                    (goal.user_commitment || 0)
                  ) / 3
                }))
                .sort((a, b) => b.avgScore - a.avgScore)
                .slice(0, 5)
                .map((goal: any, idx: number) => {
                  const readiness = getReadinessLabel(goal.avgScore)
                  const isClickable = onGoalSelected && readiness.level !== 'low'
                  return (
                    <div 
                      key={idx} 
                      className={`goal-item ${isClickable ? 'clickable' : ''}`}
                      onClick={isClickable ? () => onGoalSelected(goal.goal) : undefined}
                      title={isClickable ? 'Click to start learning this goal' : 'Continue chatting to develop this goal'}
                    >
                      <p className="goal-text">{goal.goal}</p>
                      <span className={`readiness-badge ${readiness.level}`}>
                        {readiness.label}
                      </span>
                    </div>
                  )
                })}
            </div>
          </div>
        )}

        {/* Teaching Candidates */}
        {teachingCandidates.length > 0 && (
          <div className="profile-card">
            <div className="card-header">
              <span className="card-title">Teaching Topics</span>
              <span className="item-count">{teachingCandidates.length}</span>
            </div>
            <div className="teaching-list">
              {teachingCandidates.map((tc: any, idx: number) => {
                const readiness = getReadinessLabel(tc.readiness_score)
                return (
                  <div key={idx} className="teaching-item">
                    <p className="teaching-topic">{tc.topic}</p>
                    {tc.identified_gap && (
                      <p className="teaching-gap">Gap: {tc.identified_gap}</p>
                    )}
                    <span className={`readiness-badge ${readiness.level}`}>
                      {readiness.label}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Conversational Themes */}
        {themes.length > 0 && (
          <div className="profile-card">
            <div className="card-header">
              <span className="card-title">Themes</span>
            </div>
            <div className="theme-tags">
              {themes.slice(0, 8).map((theme: any, idx: number) => (
                <span key={idx} className="theme-tag">
                  {theme.theme_seed}
                </span>
              ))}
              {themes.length > 8 && (
                <span className="theme-more">+{themes.length - 8} more</span>
              )}
            </div>
          </div>
        )}

        {/* Current Focus */}
        <div className="profile-card focus-card">
          <div className="card-header">
            <span className="card-title">Current Focus</span>
          </div>
          <div className="focus-details">
            {controller.conversation_mode && (
              <div className="focus-item">
                <span className="focus-label">Mode</span>
                <span className="focus-value mode-badge">
                  {controller.conversation_mode.replace(/_/g, ' ')}
                </span>
              </div>
            )}
            {controller.question_intent && (
              <div className="focus-item">
                <span className="focus-label">Intent</span>
                <span className="focus-value">{controller.question_intent.replace(/_/g, ' ')}</span>
              </div>
            )}
            {controller.target_ambiguity && (
              <div className="focus-item">
                <span className="focus-label">Target</span>
                <span className="focus-value target-badge">{controller.target_ambiguity}</span>
              </div>
            )}
          </div>
        </div>

        {/* Interview State */}
        <div className="profile-card state-card">
          <div className="card-header">
            <span className="card-title">Discovery State</span>
          </div>
          <div className="state-indicators">
            <div className={`state-indicator ${interviewState.goal_identified ? 'active' : ''}`}>
              <span className="state-dot"></span>
              <span className="state-label">Goal {interviewState.goal_identified ? 'Found' : 'Searching'}</span>
            </div>
            {interviewState.user_goal && (
              <p className="confirmed-goal">{interviewState.user_goal}</p>
            )}
            {interviewState.proposed_goal && !interviewState.goal_identified && (
              <p className="proposed-goal">Proposed: {interviewState.proposed_goal}</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
