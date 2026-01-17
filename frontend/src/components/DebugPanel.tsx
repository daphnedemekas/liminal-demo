import { useState, useEffect } from 'react'
import { api } from '../services/api'

interface DebugPanelProps {
  sessionId: string | null
  isConnected: boolean
}

export default function DebugPanel({ sessionId, isConnected }: DebugPanelProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [schema, setSchema] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!sessionId || !isConnected || !isOpen) return

    const fetchSchema = async () => {
      try {
        setLoading(true)
        const data = await api.getDiscoverySchema(sessionId)
        setSchema(data)
      } catch (error) {
        console.error('Failed to fetch schema:', error)
      } finally {
        setLoading(false)
      }
    }

    // Fetch immediately
    fetchSchema()

    // Poll every 2 seconds while open
    const interval = setInterval(fetchSchema, 2000)
    return () => clearInterval(interval)
  }, [sessionId, isConnected, isOpen])

  const formatValue = (value: any): string => {
    if (value === null || value === undefined) return 'unknown'
    if (typeof value === 'object') {
      if (Array.isArray(value)) {
        return value.length === 0 ? '[]' : JSON.stringify(value, null, 2)
      }
      return JSON.stringify(value, null, 2)
    }
    return String(value)
  }

  const renderSection = (title: string, data: any) => {
    if (!data) return null

    return (
      <div className="debug-section">
        <h4 className="debug-section-title">{title}</h4>
        <div className="debug-section-content">
          {typeof data === 'object' ? (
            Object.entries(data).map(([key, value]) => (
              <div key={key} className="debug-field">
                <span className="debug-field-key">{key}:</span>
                <span className="debug-field-value">{formatValue(value)}</span>
              </div>
            ))
          ) : (
            <div className="debug-field">
              <span className="debug-field-value">{formatValue(data)}</span>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className={`debug-panel ${isOpen ? 'open' : ''}`}>
      <button className="debug-toggle" onClick={() => setIsOpen(!isOpen)}>
        {isOpen ? 'Hide' : 'Show'} Debug Info
      </button>

      {isOpen && (
        <div className="debug-content">
          {loading && !schema && <div className="debug-loading">Loading...</div>}

          {schema && (
            <>
              {/* User Profile */}
              {schema.user_profile && (
                <div className="debug-category">
                  <h3 className="debug-category-title">User Profile</h3>
                  {renderSection('Curiosity Type', schema.user_profile.curiosity_type)}
                  {renderSection('Entry Mode', schema.user_profile.entry_mode)}
                  {renderSection('Uncertainty Tolerance', schema.user_profile.uncertainty_tolerance)}
                  {renderSection('Interest Phase Default', schema.user_profile.interest_phase_default)}
                  {renderSection('Pacing Preference', schema.user_profile.pacing_preference)}
                  {renderSection('RIASEC Hint', schema.user_profile.riasec_hint)}
                  {renderSection('Communication Style', schema.user_profile.communication_style)}
                </div>
              )}

              {/* Goal Candidates */}
              {schema.goal_candidates && schema.goal_candidates.length > 0 && (
                <div className="debug-category">
                  <h3 className="debug-category-title">Goal Candidates ({schema.goal_candidates.length})</h3>
                  {schema.goal_candidates.map((candidate: any, idx: number) => (
                    <div key={idx} className="debug-section">
                      <h4 className="debug-section-title">Goal {idx + 1}</h4>
                      <div className="debug-section-content">
                        <div className="debug-field">
                          <span className="debug-field-key">Goal:</span>
                          <span className="debug-field-value">{candidate.goal}</span>
                        </div>
                        <div className="debug-field">
                          <span className="debug-field-key">Concreteness:</span>
                          <span className="debug-field-value">{candidate.concreteness?.toFixed(2)}</span>
                        </div>
                        <div className="debug-field">
                          <span className="debug-field-key">Break-apartability:</span>
                          <span className="debug-field-value">{candidate.break_apartability?.toFixed(2)}</span>
                        </div>
                        <div className="debug-field">
                          <span className="debug-field-key">Scope:</span>
                          <span className="debug-field-value">{candidate.scope_appropriateness?.toFixed(2)}</span>
                        </div>
                        <div className="debug-field">
                          <span className="debug-field-key">Commitment:</span>
                          <span className="debug-field-value">{candidate.user_commitment?.toFixed(2)}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Teaching Candidates */}
              {schema.teaching_candidates && schema.teaching_candidates.length > 0 && (
                <div className="debug-category">
                  <h3 className="debug-category-title">Teaching Candidates ({schema.teaching_candidates.length})</h3>
                  {schema.teaching_candidates.map((candidate: any, idx: number) => (
                    <div key={idx} className="debug-section">
                      <h4 className="debug-section-title">Candidate {idx + 1}</h4>
                      <div className="debug-section-content">
                        <div className="debug-field">
                          <span className="debug-field-key">Topic:</span>
                          <span className="debug-field-value">{candidate.topic}</span>
                        </div>
                        <div className="debug-field">
                          <span className="debug-field-key">Focus Question:</span>
                          <span className="debug-field-value">{candidate.focus_question}</span>
                        </div>
                        <div className="debug-field">
                          <span className="debug-field-key">Readiness Score:</span>
                          <span className="debug-field-value">{candidate.readiness_score?.toFixed(2)}</span>
                        </div>
                        <div className="debug-field">
                          <span className="debug-field-key">Gap:</span>
                          <span className="debug-field-value">{candidate.identified_gap}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Conversational Themes */}
              {schema.conversational_themes && schema.conversational_themes.length > 0 && (
                <div className="debug-category">
                  <h3 className="debug-category-title">Conversational Themes ({schema.conversational_themes.length})</h3>
                  {schema.conversational_themes.map((theme: any, idx: number) => (
                    <div key={idx} className="debug-section">
                      <h4 className="debug-section-title">Theme {idx + 1}</h4>
                      <div className="debug-section-content">
                        <div className="debug-field">
                          <span className="debug-field-key">Seed:</span>
                          <span className="debug-field-value">{theme.theme_seed}</span>
                        </div>
                        <div className="debug-field">
                          <span className="debug-field-key">Type:</span>
                          <span className="debug-field-value">{theme.theme_type}</span>
                        </div>
                        <div className="debug-field">
                          <span className="debug-field-key">Hook:</span>
                          <span className="debug-field-value">{theme.disambiguated_hook}</span>
                        </div>
                        <div className="debug-field">
                          <span className="debug-field-key">Readiness:</span>
                          <span className="debug-field-value">{theme.readiness_score?.toFixed(2)}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Interview State */}
              {schema.interview_state && (
                <div className="debug-category">
                  <h3 className="debug-category-title">Interview State</h3>
                  {renderSection('Turns', schema.interview_state.turns_elapsed)}
                  <div className="debug-field">
                    <span className="debug-field-key">Goal Identified:</span>
                    <span className="debug-field-value">{schema.interview_state.goal_identified ? 'Yes' : 'No'}</span>
                  </div>
                  {schema.interview_state.user_goal && (
                    <div className="debug-field">
                      <span className="debug-field-key">User Goal:</span>
                      <span className="debug-field-value">{schema.interview_state.user_goal}</span>
                    </div>
                  )}
                  {renderSection('Topics Mentioned', schema.interview_state.topics_mentioned)}
                  {renderSection('Frameworks Offered', schema.interview_state.frameworks_offered)}
                </div>
              )}

              {/* Teaching Recommendation */}
              {schema.teaching_recommendation && (
                <div className="debug-category">
                  <h3 className="debug-category-title">Teaching Recommendation</h3>
                  <div className="debug-section-content">
                    <div className="debug-field">
                      <span className="debug-field-key">Ready:</span>
                      <span className="debug-field-value">{schema.teaching_recommendation.ready ? 'Yes' : 'No'}</span>
                    </div>
                    {schema.teaching_recommendation.ready && (
                      <>
                        <div className="debug-field">
                          <span className="debug-field-key">Target Topic:</span>
                          <span className="debug-field-value">{schema.teaching_recommendation.target_topic}</span>
                        </div>
                        <div className="debug-field">
                          <span className="debug-field-key">Focus Question:</span>
                          <span className="debug-field-value">{schema.teaching_recommendation.focus_question}</span>
                        </div>
                        <div className="debug-field">
                          <span className="debug-field-key">Angle:</span>
                          <span className="debug-field-value">{schema.teaching_recommendation.angle}</span>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              )}

              {/* Controller */}
              {schema.controller && (
                <div className="debug-category">
                  <h3 className="debug-category-title">Controller</h3>
                  <div className="debug-section-content">
                    <div className="debug-field">
                      <span className="debug-field-key">Next Action:</span>
                      <span className="debug-field-value">{schema.controller.next_action}</span>
                    </div>
                    <div className="debug-field">
                      <span className="debug-field-key">Question Intent:</span>
                      <span className="debug-field-value">{schema.controller.question_intent}</span>
                    </div>
                    <div className="debug-field">
                      <span className="debug-field-key">Branch Condition:</span>
                      <span className="debug-field-value">{schema.controller.branch_condition}</span>
                    </div>
                    {schema.controller.focus_instruction && (
                      <div className="debug-field">
                        <span className="debug-field-key">Focus Instruction:</span>
                        <span className="debug-field-value">{schema.controller.focus_instruction}</span>
                      </div>
                    )}
                    {schema.controller.conversation_mode && (
                      <div className="debug-field">
                        <span className="debug-field-key">Conversation Mode:</span>
                        <span className="debug-field-value">{schema.controller.conversation_mode}</span>
                      </div>
                    )}
                    {schema.controller.target_ambiguity && (
                      <div className="debug-field">
                        <span className="debug-field-key">Target Ambiguity:</span>
                        <span className="debug-field-value">{schema.controller.target_ambiguity}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
