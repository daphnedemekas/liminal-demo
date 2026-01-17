import { useState, useEffect, useCallback } from 'react'
import { api } from '../services/api'

interface ProfilePanelProps {
  sessionId: string | null
  isConnected: boolean
  initialSummary?: string
}

// Helper functions to convert numeric values to descriptive labels

const getReadinessLabel = (score: number | undefined): { label: string; level: string } => {
  if (score === undefined || score === null) return { label: 'Unknown', level: 'unknown' }
  if (score >= 0.7) return { label: 'Ready', level: 'high' }
  if (score >= 0.5) return { label: 'Developing', level: 'medium' }
  return { label: 'Emerging', level: 'low' }
}

const getDominantEntryMode = (entryMode: any): { mode: string; icon: string } => {
  if (!entryMode) return { mode: 'Exploring', icon: '' }
  const { people = 0, problems = 0, ideas = 0 } = entryMode
  const max = Math.max(people, problems, ideas)
  if (max < 0.3) return { mode: 'Exploring', icon: '' }
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
  
  // Handle object with value/confidence structure (like CuriosityTypeField, PacingPreferenceField, etc.)
  if (typeof trait === 'object') {
    // Check if it has the expected structure (value can be null)
    if ('value' in trait) {
      return { 
        value: trait.value || '—', 
        confidence: getConfidenceLabel(trait.confidence) 
      }
    }
    // Unknown object structure - show placeholder instead of [object Object]
    return { value: '—', confidence: '' }
  }
  
  // Simple string value
  return { value: String(trait), confidence: '' }
}

export default function ProfilePanel({ sessionId, isConnected, initialSummary }: ProfilePanelProps) {
  const [schema, setSchema] = useState<any>(null)
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
        const data = await api.getDiscoverySchema(sessionId)
        setSchema(data)
      } catch (error) {
        console.error('Failed to fetch schema:', error)
      }
    }

    fetchSchema()
    const interval = setInterval(fetchSchema, 3000)
    return () => clearInterval(interval)
  }, [sessionId, isConnected])

  const generateSummary = useCallback(async () => {
    if (!schema || !sessionId || isGeneratingSummary) return
    
    const currentTurn = schema.interview_state?.turns_elapsed || 0
    if (summary && currentTurn - lastSummaryTurn < 2) return
    
    setIsGeneratingSummary(true)
    try {
      const response = await fetch('http://localhost:8000/api/profile/summary', {
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
  }, [schema, sessionId, summary, lastSummaryTurn, isGeneratingSummary])

  useEffect(() => {
    if (schema && !summary) {
      generateSummary()
    }
  }, [schema, summary, generateSummary])

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
              onClick={generateSummary}
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
              <span className="trait-icon"></span>
              <span className="trait-label">Curiosity</span>
              <span className="trait-value">{curiosity.value}</span>
              {curiosity.confidence && <span className="trait-confidence">{curiosity.confidence}</span>}
            </div>
            <div className="trait-item">
              <span className="trait-icon"></span>
              <span className="trait-label">Pacing</span>
              <span className="trait-value">{pacing.value}</span>
            </div>
            <div className="trait-item">
              <span className="trait-icon"></span>
              <span className="trait-label">Uncertainty</span>
              <span className="trait-value">{uncertainty.value}</span>
            </div>
            <div className="trait-item">
              <span className="trait-icon"></span>
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
              <span className="item-count">{goalCandidates.length}</span>
            </div>
            <div className="goal-list">
              {goalCandidates.map((goal: any, idx: number) => {
                const avgScore = (
                  (goal.concreteness || 0) + 
                  (goal.scope_appropriateness || 0) + 
                  (goal.user_commitment || 0)
                ) / 3
                const readiness = getReadinessLabel(avgScore)
                return (
                  <div key={idx} className="goal-item">
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
