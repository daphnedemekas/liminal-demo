import { useState, useEffect, useCallback } from 'react'
import { api, TeachingSchema, UnderstandingMarker } from '../services/api'
import { stripMarkdown } from '../utils/textUtils'
import { getApiBaseUrl } from '../config'

interface ProfilePanelProps {
  sessionId: string | null
  isConnected: boolean
  initialSummary?: string
  isTeachingSession?: boolean
  onGoalSelected?: (goalText: string) => void
  onTeachingCandidateClick?: (candidate: any) => void
  onSchemaUpdate?: (listener: (schema: any) => void) => () => void
}

// Helper functions to convert numeric values to descriptive labels

const getReadinessLabel = (score: number | undefined): { label: string; level: string } => {
  if (score === undefined || score === null) return { label: 'Unknown', level: 'unknown' }
  if (score >= 0.7) return { label: 'Explore', level: 'high' }
  if (score >= 0.5) return { label: 'Taking shape', level: 'medium' }
  return { label: 'Just starting', level: 'low' }
}

// @ts-ignore - unused for now, may be needed later
const _getDominantEntryMode = (entryMode: any): { mode: string; icon: string } => {
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

// @ts-ignore - unused for now, may be needed later
const _formatTraitValue = (trait: any): { value: string; confidence: string } => {
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
      return { label: 'Taking shape', className: 'marker-developing' }
    default:
      return { label: 'Not Yet', className: 'marker-not-yet' }
  }
}

export default function ProfilePanel({ sessionId, isConnected, initialSummary, isTeachingSession = false, onGoalSelected, onTeachingCandidateClick, onSchemaUpdate }: ProfilePanelProps) {
  const [schema, setSchema] = useState<any>(null)
  const [teachingSchema, setTeachingSchema] = useState<TeachingSchema | null>(null)
  const [summary, setSummary] = useState<string>(initialSummary || '')
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false)
  const [lastSummaryTurn, setLastSummaryTurn] = useState(initialSummary ? 0 : -1)
  
  // AI Reasoning / Inner Monologue
  const [aiReasoning, setAiReasoning] = useState<string>('')
  const [isGeneratingReasoning, setIsGeneratingReasoning] = useState(false)
  const [lastReasoningTurn, setLastReasoningTurn] = useState(-1)

  useEffect(() => {
    if (initialSummary) {
      setSummary(initialSummary)
      setLastSummaryTurn(0)
    }
  }, [initialSummary])

  // Fetch schema once on mount, then listen for WebSocket-driven updates
  useEffect(() => {
    if (!sessionId || !isConnected) return

    const fetchSchema = async () => {
      try {
        if (isTeachingSession) {
          const data = await api.getTeachingState(sessionId)
          setTeachingSchema(data)
          if (data.narrative_summary) {
            setSummary(data.narrative_summary)
          }
        } else {
          const data = await api.getDiscoverySchema(sessionId)
          setSchema(data)
        }
      } catch (_) {
        // Schema fetch failed, will retry on next update
      }
    }

    // Initial fetch
    fetchSchema()

    // Subscribe to WebSocket-driven schema updates (no more polling)
    if (onSchemaUpdate) {
      const unsubscribe = onSchemaUpdate((updatedSchema) => {
        if (isTeachingSession) {
          setTeachingSchema(updatedSchema)
          if (updatedSchema.narrative_summary) {
            setSummary(updatedSchema.narrative_summary)
          }
        } else {
          setSchema(updatedSchema)
        }
      })
      return unsubscribe
    }

    // Fallback: poll every 10s if no WebSocket schema subscription available
    const interval = setInterval(fetchSchema, 10000)
    return () => clearInterval(interval)
  }, [sessionId, isConnected, isTeachingSession, onSchemaUpdate])

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
      const apiUrl = getApiBaseUrl()
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
        } catch (_) {
          // Summary save failed
        }
      }
    } catch (_) {
      // Summary generation failed
    } finally {
      setIsGeneratingSummary(false)
    }
  }, [schema, sessionId, summary, lastSummaryTurn, isGeneratingSummary, isTeachingSession])

  // Auto-generate summary on first load and every 2 turns
  // Delay first generation to let the main chat response complete first
  useEffect(() => {
    if (schema && !isTeachingSession) {
      const currentTurn = schema.interview_state?.turns_elapsed || 0
      // Generate if no summary OR if enough turns have passed
      if (!summary || currentTurn - lastSummaryTurn >= 2) {
        // Delay summary generation to prioritize chat response
        const delay = !summary ? 3000 : 0  // 3s delay for first summary
        const timer = setTimeout(() => generateSummary(), delay)
        return () => clearTimeout(timer)
      }
    }
  }, [schema, isTeachingSession]) // Intentionally exclude summary and lastSummaryTurn to allow re-generation

  // Generate AI reasoning / inner monologue
  const generateReasoning = useCallback(async () => {
    if (isTeachingSession || !schema || !sessionId || isGeneratingReasoning) return

    const currentTurn = schema.interview_state?.turns_elapsed || 0

    // Skip if we already have reasoning for this turn
    if (aiReasoning && currentTurn === lastReasoningTurn) return
    setIsGeneratingReasoning(true)
    try {
      const apiUrl = getApiBaseUrl()
      const response = await fetch(`${apiUrl}/api/profile/reasoning`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ schema, session_id: sessionId })
      })
      if (response.ok) {
        const data = await response.json()
        setAiReasoning(data.reasoning)
        setLastReasoningTurn(currentTurn)
      }
    } catch (_) {
      // Reasoning generation failed
    } finally {
      setIsGeneratingReasoning(false)
    }
  }, [schema, sessionId, aiReasoning, lastReasoningTurn, isGeneratingReasoning, isTeachingSession])

  // Auto-generate reasoning on schema change
  // Delay first generation to let the main chat response complete first
  useEffect(() => {
    if (schema && !isTeachingSession) {
      const currentTurn = schema.interview_state?.turns_elapsed || 0
      if (!aiReasoning || currentTurn !== lastReasoningTurn) {
        // Delay reasoning generation to prioritize chat response
        const delay = !aiReasoning ? 4000 : 0  // 4s delay for first reasoning
        const timer = setTimeout(() => generateReasoning(), delay)
        return () => clearTimeout(timer)
      }
    }
  }, [schema, isTeachingSession]) // Intentionally minimal deps for re-generation

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
                <span className="card-title">Project Path</span>
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
          <h2>Profile</h2>
        </div>
        <div className="profile-panel-content">
          <div className="profile-card empty-state">
            <p>Waiting for conversation data...</p>
          </div>
        </div>
      </div>
    )
  }

  const goalCandidates = schema.goal_candidates || []
  const teachingCandidates = schema.teaching_candidates || []
  const themes = schema.conversational_themes || []
  const interviewState = schema.interview_state || {}
  // @ts-ignore - unused for now, may be needed later
  const _controller = schema.controller || {}
  const priorKnowledgeAssessment = schema.prior_knowledge_assessment || {}

  return (
    <div className="profile-panel">
      <div className="profile-panel-header">
        <h2>Profile</h2>
        <span className="turn-counter">Turn {interviewState.turns_elapsed || 0}</span>
      </div>

      <div className="profile-panel-content">
        {/* Summary Card */}
        <div className="profile-card summary-card">
          <div className="card-header">
            <span className="card-title">Summary</span>
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
              : summary || 'Continue the conversation to build your project profile.'}
          </p>
        </div>

        {/* Prior Knowledge Assessment (when available) */}
        {priorKnowledgeAssessment.assessed_level && (
          <div className="profile-card assessment-card">
            <div className="card-header">
              <span className="card-title">Prior Knowledge</span>
              <span className={`level-badge ${priorKnowledgeAssessment.assessed_level}`}>
                {priorKnowledgeAssessment.assessed_level}
              </span>
            </div>
            <div className="assessment-details">
              {/* NEW: Granular concepts with proficiency levels */}
              {priorKnowledgeAssessment.concept_knowledge?.length > 0 && (
                <div className="assessment-section">
                  <span className="assessment-label">Concept Knowledge</span>
                  <div className="concept-knowledge-list">
                    {priorKnowledgeAssessment.concept_knowledge.map((ck: { concept: string; proficiency: string; evidence?: string }, idx: number) => (
                      <div key={idx} className={`concept-knowledge-item proficiency-${ck.proficiency}`} title={ck.evidence || ''}>
                        <span className="concept-name">{ck.concept}</span>
                        <span className={`proficiency-badge ${ck.proficiency}`}>
                          {ck.proficiency === 'heard_of' && '👂 Heard of'}
                          {ck.proficiency === 'understands_basics' && '📖 Basics'}
                          {ck.proficiency === 'can_explain' && '💬 Can explain'}
                          {ck.proficiency === 'can_apply' && '🛠️ Can apply'}
                          {ck.proficiency === 'expert' && '⭐ Expert'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {/* LEGACY: Simple concept lists (fallback if no granular data) */}
              {(!priorKnowledgeAssessment.concept_knowledge || priorKnowledgeAssessment.concept_knowledge.length === 0) && priorKnowledgeAssessment.concepts_known?.length > 0 && (
                <div className="assessment-section">
                  <span className="assessment-label">Concepts Known</span>
                  <div className="concept-tags">
                    {priorKnowledgeAssessment.concepts_known.map((concept: string, idx: number) => (
                      <span key={idx} className="concept-tag known">{concept}</span>
                    ))}
                  </div>
                </div>
              )}
              {priorKnowledgeAssessment.concepts_unclear?.length > 0 && (
                <div className="assessment-section">
                  <span className="assessment-label">Needs Clarification</span>
                  <div className="concept-tags">
                    {priorKnowledgeAssessment.concepts_unclear.map((concept: string, idx: number) => (
                      <span key={idx} className="concept-tag unclear">{concept}</span>
                    ))}
                  </div>
                </div>
              )}
              {priorKnowledgeAssessment.practical_experience && (
                <div className="assessment-section">
                  <span className="assessment-label">Experience</span>
                  <p className="assessment-text">{priorKnowledgeAssessment.practical_experience}</p>
                </div>
              )}
              {priorKnowledgeAssessment.learning_style_hints?.length > 0 && (
                <div className="assessment-section">
                  <span className="assessment-label">Learning Style</span>
                  <div className="style-tags">
                    {priorKnowledgeAssessment.learning_style_hints.map((hint: string, idx: number) => (
                      <span key={idx} className="style-tag">{hint}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Goal Candidates */}
        {goalCandidates.length > 0 && (
          <div className="profile-card">
            <div className="card-header">
              <span className="card-title">Early Ideas</span>
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
              <span className="card-title">Suggested Deep Dives</span>
              <span className="item-count">{teachingCandidates.length}</span>
            </div>
            <div className="goal-list">
              {/* Sort by readiness score (descending) */}
              {[...teachingCandidates]
                .sort((a: any, b: any) => (b.readiness_score || 0) - (a.readiness_score || 0))
                .map((tc: any, idx: number) => {
                  const readiness = getReadinessLabel(tc.readiness_score)
                  const isClickable = onTeachingCandidateClick && readiness.level !== 'low'
                  return (
                    <div 
                      key={tc.id || idx} 
                      className={`goal-item ${isClickable ? 'clickable' : ''}`}
                      onClick={isClickable ? () => onTeachingCandidateClick(tc) : undefined}
                      title={isClickable ? 'Click to start learning this topic' : 'Continue chatting to develop this topic'}
                    >
                      <div className="goal-item-content">
                        <p className="goal-text">{stripMarkdown(tc.topic)}</p>
                        {tc.identified_gap && (
                          <p className="goal-subtext" style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                            {stripMarkdown(tc.identified_gap.length > 60 ? tc.identified_gap.substring(0, 60) + '...' : tc.identified_gap)}
                          </p>
                        )}
                      </div>
                      <span className={`readiness-badge ${readiness.level}`}>
                        {readiness.label}
                      </span>
                    </div>
                  )
                })}
            </div>
          </div>
        )}

        {/* AI Inner Monologue */}
        <div className="profile-card inner-monologue-card">
          <div className="card-header">
            <span className="card-title">AI Thinking</span>
            {isGeneratingReasoning && <span className="generating-indicator">...</span>}
          </div>
          <div className="inner-monologue">
            <p className="monologue-text">
              {isGeneratingReasoning && !aiReasoning 
                ? 'Processing...' 
                : aiReasoning || 'Getting to know you...'}
            </p>
          </div>
        </div>

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
      </div>
    </div>
  )
}
