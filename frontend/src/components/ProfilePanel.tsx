import { useState, useEffect, useCallback } from 'react'
import { api } from '../services/api'

interface ProfilePanelProps {
  sessionId: string | null
  isConnected: boolean
  initialSummary?: string  // Pre-loaded summary for resumed sessions
}

export default function ProfilePanel({ sessionId, isConnected, initialSummary }: ProfilePanelProps) {
  const [schema, setSchema] = useState<any>(null)
  const [summary, setSummary] = useState<string>(initialSummary || '')
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false)
  const [lastSummaryTurn, setLastSummaryTurn] = useState(initialSummary ? 0 : -1)
  
  // Update summary when initialSummary prop changes (session switch)
  useEffect(() => {
    if (initialSummary) {
      setSummary(initialSummary)
      setLastSummaryTurn(0)
    }
  }, [initialSummary])

  // Fetch schema data
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

  // Generate summary when significant changes occur
  const generateSummary = useCallback(async () => {
    if (!schema || !sessionId || isGeneratingSummary) return
    
    const currentTurn = schema.interview_state?.turns_elapsed || 0
    // Only regenerate every 2 turns or if we have no summary
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
        
        // Persist the summary to database
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

  // Helper to convert numeric value to readable label
  const toLevel = (value: number | null | undefined, type: 'strength' | 'level' = 'level'): string => {
    if (value === null || value === undefined) return '—'
    if (type === 'strength') {
      if (value >= 0.7) return 'Strong'
      if (value >= 0.4) return 'Moderate'
      if (value > 0) return 'Weak'
      return '—'
    }
    if (value >= 0.7) return 'High'
    if (value >= 0.4) return 'Medium'
    if (value > 0) return 'Low'
    return '—'
  }

  const toLevelClass = (value: number | null | undefined): string => {
    if (value === null || value === undefined) return 'unknown'
    if (value >= 0.7) return 'high'
    if (value >= 0.4) return 'medium'
    if (value > 0) return 'low'
    return 'unknown'
  }

  // Get confidence indicator
  const getConfidence = (obj: any): string => {
    if (!obj?.confidence) return ''
    const conf = obj.confidence
    if (conf >= 0.7) return '●●●'
    if (conf >= 0.4) return '●●○'
    if (conf > 0) return '●○○'
    return '○○○'
  }

  if (!schema) {
    return (
      <div className="profile-panel">
        <div className="profile-panel-header">
          <h2>📊 Learner Profile</h2>
        </div>
        <div className="profile-panel-loading">
          <p>Waiting for conversation data...</p>
        </div>
      </div>
    )
  }

  const profile = schema.user_profile
  const interviewState = schema.interview_state
  const goalCandidates = schema.goal_candidates || []
  const themes = schema.conversational_themes || []

  return (
    <div className="profile-panel">
      <div className="profile-panel-header">
        <h2>📊 Learner Profile</h2>
        <span className="turn-counter">Turn {interviewState?.turns_elapsed || 0}</span>
      </div>

      <div className="profile-panel-content">
        {/* AI Summary */}
        <div className="profile-summary">
          <div className="profile-summary-header">
            <span className="summary-icon">✨</span>
            <span>Profile Summary</span>
            <button 
              className="refresh-summary-btn"
              onClick={generateSummary}
              disabled={isGeneratingSummary}
              title="Refresh summary"
            >
              {isGeneratingSummary ? '...' : '↻'}
            </button>
          </div>
          <p className="profile-summary-text">
            {isGeneratingSummary && !summary 
              ? 'Analyzing conversation...' 
              : summary || 'Continue the conversation to build your learner profile.'}
          </p>
        </div>

        {/* Goal Status */}
        {(interviewState?.user_goal || goalCandidates.length > 0) && (
          <div className="profile-section">
            <h3 className="profile-section-title">🎯 Learning Goal</h3>
            {interviewState?.user_goal ? (
              <div className="goal-confirmed">
                <span className="goal-badge confirmed">Confirmed</span>
                <p className="goal-text">{interviewState.user_goal}</p>
              </div>
            ) : goalCandidates.length > 0 ? (
              <div className="goal-candidates">
                <span className="goal-badge exploring">Exploring</span>
                {goalCandidates.slice(0, 2).map((g: any, i: number) => (
                  <div key={i} className="goal-candidate-item">
                    <span className="goal-candidate-text">{g.goal}</span>
                    <div className="goal-metrics">
                      <span className={`metric ${toLevelClass(g.concreteness)}`}>
                        Clarity: {toLevel(g.concreteness)}
                      </span>
                      <span className={`metric ${toLevelClass(g.user_commitment)}`}>
                        Commitment: {toLevel(g.user_commitment)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        )}

        {/* Curiosity Profile */}
        {profile && (
          <div className="profile-section">
            <h3 className="profile-section-title">🧠 Curiosity Profile</h3>
            
            <div className="profile-item">
              <span className="profile-label">Curiosity Type</span>
              <span className="profile-value">
                {profile.curiosity_type?.value || '—'}
                <span className="confidence-dots">{getConfidence(profile.curiosity_type)}</span>
              </span>
            </div>

            <div className="profile-item">
              <span className="profile-label">Entry Mode</span>
              <div className="entry-mode-bars">
                {profile.entry_mode && (
                  <>
                    <div className="entry-bar">
                      <span className="entry-label">Ideas</span>
                      <div className={`entry-fill ${toLevelClass(profile.entry_mode.ideas)}`} 
                           style={{ width: `${(profile.entry_mode.ideas || 0) * 100}%` }} />
                    </div>
                    <div className="entry-bar">
                      <span className="entry-label">Problems</span>
                      <div className={`entry-fill ${toLevelClass(profile.entry_mode.problems)}`}
                           style={{ width: `${(profile.entry_mode.problems || 0) * 100}%` }} />
                    </div>
                    <div className="entry-bar">
                      <span className="entry-label">People</span>
                      <div className={`entry-fill ${toLevelClass(profile.entry_mode.people)}`}
                           style={{ width: `${(profile.entry_mode.people || 0) * 100}%` }} />
                    </div>
                  </>
                )}
              </div>
            </div>

            <div className="profile-item">
              <span className="profile-label">Uncertainty Tolerance</span>
              <span className={`profile-value badge ${toLevelClass(
                profile.uncertainty_tolerance?.value === 'high' ? 0.8 :
                profile.uncertainty_tolerance?.value === 'medium' ? 0.5 :
                profile.uncertainty_tolerance?.value === 'low' ? 0.2 : null
              )}`}>
                {profile.uncertainty_tolerance?.value || '—'}
              </span>
            </div>

            <div className="profile-item">
              <span className="profile-label">Pacing</span>
              <span className="profile-value">
                {profile.pacing_preference?.value === 'fast_resolution' ? 'Quick learner' :
                 profile.pacing_preference?.value === 'exploratory' ? 'Exploratory' :
                 profile.pacing_preference?.value === 'mixed' ? 'Balanced' : '—'}
              </span>
            </div>
          </div>
        )}

        {/* Motivation */}
        {profile?.motivation_profile && (
          <div className="profile-section">
            <h3 className="profile-section-title">💡 Motivation</h3>
            <div className="motivation-grid">
              <div className={`motivation-item ${toLevelClass(profile.motivation_profile.intrinsic_value)}`}>
                <span className="motivation-label">Intrinsic</span>
                <span className="motivation-value">{toLevel(profile.motivation_profile.intrinsic_value, 'strength')}</span>
              </div>
              <div className={`motivation-item ${toLevelClass(profile.motivation_profile.utility_value)}`}>
                <span className="motivation-label">Utility</span>
                <span className="motivation-value">{toLevel(profile.motivation_profile.utility_value, 'strength')}</span>
              </div>
              <div className={`motivation-item ${toLevelClass(profile.motivation_profile.identity_value)}`}>
                <span className="motivation-label">Identity</span>
                <span className="motivation-value">{toLevel(profile.motivation_profile.identity_value, 'strength')}</span>
              </div>
            </div>
          </div>
        )}

        {/* Active Themes */}
        {themes.length > 0 && (
          <div className="profile-section">
            <h3 className="profile-section-title">Active Themes</h3>
            <div className="themes-list">
              {themes.slice(0, 4).map((theme: any, i: number) => (
                <div key={i} className="theme-tag">
                  <span className="theme-type">{theme.theme_type}</span>
                  <span className="theme-seed">{theme.theme_seed}</span>
                </div>
              ))}
              {themes.length > 4 && (
                <span className="themes-more">+{themes.length - 4} more</span>
              )}
            </div>
          </div>
        )}

        {/* Controller State (Compact) */}
        {schema.controller && (
          <div className="profile-section controller-section">
            <h3 className="profile-section-title">Current Focus</h3>
            <div className="controller-info">
              <span className="controller-mode">{schema.controller.conversation_mode || 'exploring'}</span>
              {schema.controller.target_ambiguity && (
                <span className="controller-target">→ {schema.controller.target_ambiguity}</span>
              )}
            </div>
            {schema.controller.question_intent && (
              <p className="controller-intent">{schema.controller.question_intent}</p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

