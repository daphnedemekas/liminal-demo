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

  const getActiveFocus = (controller: any) => {
    if (!controller) return 'neutral'
    
    const intent = (controller.question_intent || '').toLowerCase()
    const focus = (controller.focus_instruction || '').toLowerCase()
    const combined = `${intent} ${focus}`

    if (combined.includes('pacing') || combined.includes('fast') || combined.includes('slow')) 
      return 'profile-pacing'
    if (combined.includes('uncertainty') || combined.includes('ambiguity') || combined.includes('unknown')) 
      return 'profile-uncertainty'
    if (combined.includes('goal') || combined.includes('outcome') || combined.includes('achieve')) 
      return 'goals'
    if (combined.includes('curiosity') || combined.includes('interest') || combined.includes('explore')) 
      return 'profile-curiosity'
    if (combined.includes('motivation') || combined.includes('why') || combined.includes('drive'))
      return 'profile-motivation'
    
    return 'neutral'
  }

  if (!schema) {
    return (
      <div className="profile-panel">
        <div className="profile-panel-header">
          <h2>Learner Profile</h2>
        </div>
        <div className="profile-panel-loading">
          <p>Waiting for conversation data...</p>
        </div>
      </div>
    )
  }

  const activeFocus = getActiveFocus(schema.controller)
  const profile = schema.user_profile || {}
  const goalCandidates = schema.goal_candidates || []
  const interviewState = schema.interview_state

  return (
    <div className="profile-panel visual-model">
      <div className="profile-panel-header">
        <h2>Insight Map</h2>
        <span className="turn-counter">Turn {interviewState?.turns_elapsed || 0}</span>
      </div>

      <div className="profile-panel-content">
        {/* Summary */}
        <div className="profile-summary">
          <div className="profile-summary-header">
            <span>Current Understanding</span>
            <button 
              className="refresh-summary-btn"
              onClick={generateSummary}
              disabled={isGeneratingSummary}
              title="Refresh summary"
            >
              {isGeneratingSummary ? '...' : 'Refresh'}
            </button>
          </div>
          <p className="profile-summary-text">
            {isGeneratingSummary && !summary 
              ? 'Analyzing conversation...' 
              : summary || 'Continue the conversation to build your learner profile.'}
          </p>
        </div>

        {/* 1. THE CORE: User Traits */}
        <div className="vm-section vm-core">
          <h3 className="vm-title">Core Identity</h3>
          <div className="vm-traits-grid">
            <TraitCard 
              label="Pacing" 
              value={profile.pacing_preference?.value}
              isActive={activeFocus === 'profile-pacing'} 
            />
            <TraitCard 
              label="Uncertainty" 
              value={profile.uncertainty_tolerance?.value}
              isActive={activeFocus === 'profile-uncertainty'} 
            />
            <TraitCard 
              label="Curiosity" 
              value={profile.curiosity_type?.value}
              isActive={activeFocus === 'profile-curiosity'} 
            />
            <TraitCard 
              label="Motivation" 
              value={profile.motivation_profile?.primary_driver}
              isActive={activeFocus === 'profile-motivation'} 
            />
          </div>
        </div>

        {/* 2. THE HORIZON: Possibilities */}
        <div className={`vm-section vm-horizon ${activeFocus === 'goals' ? 'active-section' : ''}`}>
          <h3 className="vm-title">Horizon</h3>
          <div className="vm-bubbles-container">
            {goalCandidates.length === 0 ? (
              <div className="vm-empty-state">Exploring possibilities...</div>
            ) : (
              goalCandidates.map((goal: any, i: number) => (
                <GoalBubble 
                  key={i} 
                  goal={goal} 
                  isActive={activeFocus === 'goals'}
                  index={i}
                />
              ))
            )}
          </div>
        </div>
        
        {/* 3. THE LENS: Current Focus */}
        <div className="vm-status-bar">
          <span className="vm-status-label">Current Focus:</span>
          <span className="vm-status-value">
             {schema.controller?.question_intent || 'Observing...'}
          </span>
        </div>
      </div>
    </div>
  )
}

function TraitCard({ label, value, isActive }: { label: string, value: string | null, isActive: boolean }) {
  const isKnown = value !== null && value !== undefined
  
  // Format value for display
  let displayValue = value
  if (displayValue === 'fast_resolution') displayValue = 'Quick'
  if (displayValue === 'exploratory') displayValue = 'Exploratory'
  if (displayValue === 'mixed') displayValue = 'Balanced'
  
  return (
    <div className={`vm-trait-card ${isActive ? 'active' : ''} ${isKnown ? 'known' : 'unknown'}`}>
      <span className="vm-trait-label">{label}</span>
      <span className="vm-trait-value">{displayValue || '...'}</span>
      {isActive && <div className="vm-pulse-ring"></div>}
    </div>
  )
}

function GoalBubble({ goal, isActive, index }: { goal: any, isActive: boolean, index: number }) {
  // Size based on concreteness
  const size = 60 + ((goal.concreteness || 0) * 40)
  
  return (
    <div 
      className={`vm-goal-bubble ${isActive ? 'active' : ''}`}
      style={{ 
        width: `${size}px`, 
        height: `${size}px`,
        animationDelay: `${index * 0.2}s` 
      }}
      title={goal.goal}
    >
      <span className="vm-goal-text">{goal.goal.split(' ').slice(0, 3).join(' ')}...</span>
    </div>
  )
}
