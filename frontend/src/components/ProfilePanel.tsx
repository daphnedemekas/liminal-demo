import { useState, useEffect, useCallback } from 'react'
import { api } from '../services/api'

interface ProfilePanelProps {
  sessionId: string | null
  isConnected: boolean
  initialSummary?: string
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

  const formatValue = (value: any): string => {
    if (value === null || value === undefined) return '—'
    if (typeof value === 'object') {
      if (Array.isArray(value)) {
        return value.length === 0 ? '[]' : JSON.stringify(value, null, 2)
      }
      return JSON.stringify(value, null, 2)
    }
    return String(value)
  }

  if (!schema) {
    return (
      <div className="profile-panel">
        <div className="profile-panel-header">
          <h2>Learner Profile</h2>
        </div>
        <div className="profile-panel-content">
          <p style={{ color: '#888', padding: '10px' }}>Waiting for conversation data...</p>
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

  return (
    <div className="profile-panel">
      <div className="profile-panel-header">
        <h2>Learner Profile</h2>
        <span className="turn-counter">Turn {interviewState.turns_elapsed || 0}</span>
      </div>

      <div className="profile-panel-content">
        {/* Summary Section */}
        <div className="debug-category">
          <div className="debug-category-header">
            <h3 className="debug-category-title">Summary</h3>
            <button 
              className="refresh-btn"
              onClick={generateSummary}
              disabled={isGeneratingSummary}
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

        {/* User Profile */}
        <div className="debug-category">
          <h3 className="debug-category-title">User Profile</h3>
          <div className="debug-section-content">
            <div className="debug-field">
              <span className="debug-field-key">Curiosity:</span>
              <span className="debug-field-value">{formatValue(profile.curiosity_type?.value)}</span>
            </div>
            <div className="debug-field">
              <span className="debug-field-key">Entry Mode:</span>
              <span className="debug-field-value">
                people: {profile.entry_mode?.people?.toFixed(1) || '—'}, 
                problems: {profile.entry_mode?.problems?.toFixed(1) || '—'}, 
                ideas: {profile.entry_mode?.ideas?.toFixed(1) || '—'}
              </span>
            </div>
            <div className="debug-field">
              <span className="debug-field-key">Uncertainty:</span>
              <span className="debug-field-value">{formatValue(profile.uncertainty_tolerance?.value)}</span>
            </div>
            <div className="debug-field">
              <span className="debug-field-key">Pacing:</span>
              <span className="debug-field-value">{formatValue(profile.pacing_preference?.value)}</span>
            </div>
            <div className="debug-field">
              <span className="debug-field-key">Motivation:</span>
              <span className="debug-field-value">{formatValue(profile.motivation_profile?.primary_driver)}</span>
            </div>
          </div>
        </div>

        {/* Goal Candidates */}
        {goalCandidates.length > 0 && (
          <div className="debug-category">
            <h3 className="debug-category-title">Goal Candidates ({goalCandidates.length})</h3>
            {goalCandidates.map((goal: any, idx: number) => (
              <div key={idx} className="debug-section">
                <div className="debug-section-content">
                  <div className="debug-field">
                    <span className="debug-field-key">Goal:</span>
                    <span className="debug-field-value">{goal.goal}</span>
                  </div>
                  <div className="debug-field">
                    <span className="debug-field-key">Scores:</span>
                    <span className="debug-field-value">
                      concrete: {goal.concreteness?.toFixed(2)}, 
                      scope: {goal.scope_appropriateness?.toFixed(2)}, 
                      commit: {goal.user_commitment?.toFixed(2)}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Teaching Candidates */}
        {teachingCandidates.length > 0 && (
          <div className="debug-category">
            <h3 className="debug-category-title">Teaching Candidates ({teachingCandidates.length})</h3>
            {teachingCandidates.map((tc: any, idx: number) => (
              <div key={idx} className="debug-section">
                <div className="debug-section-content">
                  <div className="debug-field">
                    <span className="debug-field-key">Topic:</span>
                    <span className="debug-field-value">{tc.topic}</span>
                  </div>
                  <div className="debug-field">
                    <span className="debug-field-key">Gap:</span>
                    <span className="debug-field-value">{tc.identified_gap || '—'}</span>
                  </div>
                  <div className="debug-field">
                    <span className="debug-field-key">Readiness:</span>
                    <span className="debug-field-value">{tc.readiness_score?.toFixed(2)}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Conversational Themes */}
        {themes.length > 0 && (
          <div className="debug-category">
            <h3 className="debug-category-title">Themes ({themes.length})</h3>
            {themes.slice(0, 5).map((theme: any, idx: number) => (
              <div key={idx} className="debug-field">
                <span className="debug-field-key">{theme.theme_type}:</span>
                <span className="debug-field-value">{theme.theme_seed}</span>
              </div>
            ))}
            {themes.length > 5 && (
              <div className="debug-field">
                <span className="debug-field-value" style={{ fontStyle: 'italic' }}>
                  +{themes.length - 5} more...
                </span>
              </div>
            )}
          </div>
        )}

        {/* Controller State */}
        <div className="debug-category">
          <h3 className="debug-category-title">Controller</h3>
          <div className="debug-section-content">
            <div className="debug-field">
              <span className="debug-field-key">Mode:</span>
              <span className="debug-field-value">{controller.conversation_mode || '—'}</span>
            </div>
            <div className="debug-field">
              <span className="debug-field-key">Intent:</span>
              <span className="debug-field-value">{controller.question_intent || '—'}</span>
            </div>
            <div className="debug-field">
              <span className="debug-field-key">Target:</span>
              <span className="debug-field-value">{controller.target_ambiguity || '—'}</span>
            </div>
            {controller.focus_instruction && (
              <div className="debug-field">
                <span className="debug-field-key">Focus:</span>
                <span className="debug-field-value">{controller.focus_instruction}</span>
              </div>
            )}
          </div>
        </div>

        {/* Interview State */}
        <div className="debug-category">
          <h3 className="debug-category-title">State</h3>
          <div className="debug-section-content">
            <div className="debug-field">
              <span className="debug-field-key">Goal Identified:</span>
              <span className="debug-field-value">{interviewState.goal_identified ? 'Yes' : 'No'}</span>
            </div>
            {interviewState.user_goal && (
              <div className="debug-field">
                <span className="debug-field-key">User Goal:</span>
                <span className="debug-field-value">{interviewState.user_goal}</span>
              </div>
            )}
            {interviewState.proposed_goal && (
              <div className="debug-field">
                <span className="debug-field-key">Proposed:</span>
                <span className="debug-field-value">{interviewState.proposed_goal}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
