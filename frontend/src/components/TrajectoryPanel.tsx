import { useCallback, useEffect, useState } from 'react'
import { api, LearnerTrajectoryDashboard } from '../services/api'

interface TrajectoryPanelProps {
  userId: string
}

export default function TrajectoryPanel({ userId }: TrajectoryPanelProps) {
  const [data, setData] = useState<LearnerTrajectoryDashboard | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const d = await api.getTrajectory(userId)
      setData(d)
    } catch (e: any) {
      setError(e?.message || 'Failed to load trajectory')
    } finally {
      setIsLoading(false)
    }
  }, [userId])

  const refresh = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const d = await api.refreshTrajectory(userId)
      setData(d)
    } catch (e: any) {
      setError(e?.message || 'Failed to refresh trajectory')
    } finally {
      setIsLoading(false)
    }
  }, [userId])

  useEffect(() => {
    load()
  }, [load])

  const renderTimeline = (values: any[], label: string) => {
    if (!values || values.length === 0) return null
    
    return (
      <div className="trait-timeline">
        <span className="trait-label">{label}</span>
        <div className="timeline-values">
          {values.map((v, idx) => (
            <span key={idx} className="timeline-point" title={`Turn ${idx}`}>
              {typeof v === 'object' ? JSON.stringify(v) : String(v || '—')}
            </span>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="profile-panel">
      <div className="profile-panel-header">
        <h2>Trajectory</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {data?.updated_at && <span className="turn-counter">Updated</span>}
          <button className="refresh-btn" onClick={refresh} disabled={isLoading} title="Refresh trajectory">
            {isLoading ? '...' : '↻'}
          </button>
        </div>
      </div>

      <div className="profile-panel-content">
        {error && (
          <div className="profile-card warning-card">
            <p>{error}</p>
          </div>
        )}

        {!data && !error && (
          <div className="profile-card empty-state">
            <p>{isLoading ? 'Loading trajectory...' : 'No trajectory yet.'}</p>
          </div>
        )}

        {data && (
          <>
            {/* Cross-Cutting Insights */}
            {data.insights && (
              <div className="profile-card summary-card">
                <div className="card-header">
                  <span className="card-title">Insights</span>
                </div>
                <p className="summary-text">{data.insights}</p>
              </div>
            )}

            {/* Goals */}
            <div className="profile-card">
              <div className="card-header">
                <span className="card-title">Goals</span>
                <span className="item-count">{data.goals?.length || 0}</span>
              </div>
              {(!data.goals || data.goals.length === 0) && (
                <p className="summary-text">Goals will appear here after you accept one.</p>
              )}
              {data.goals?.map((g) => (
                <div key={g.goal_id} className="teaching-item">
                  <p className="teaching-topic">{g.goal_text}</p>
                  <p className="teaching-gap">
                    Status: {g.status} · Momentum: {g.momentum}
                  </p>
                  {g.learning_summary && <p className="summary-text">{g.learning_summary}</p>}
                  {g.next_suggested_move && <p className="summary-text">Next: {g.next_suggested_move}</p>}
                </div>
              ))}
            </div>

            {/* Highlights */}
            <div className="profile-card">
              <div className="card-header">
                <span className="card-title">Highlights</span>
                <span className="item-count">{data.highlights?.length || 0}</span>
              </div>
              {(!data.highlights || data.highlights.length === 0) && (
                <p className="summary-text">Highlights will appear when the system detects meaningful learning or changes.</p>
              )}
              <div className="open-questions-list">
                {data.highlights
                  ?.slice()
                  .reverse()
                  .slice(0, 12)
                  .map((h, idx) => (
                    <div key={h.id || `${h.kind}-${idx}`} className="open-question">
                      <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                        <span className="readiness-badge medium">{h.kind}</span>
                        <span>{h.summary}</span>
                      </div>
                      {h.evidence_quote && <p className="marker-evidence">"{h.evidence_quote}"</p>}
                    </div>
                  ))}
              </div>
            </div>

            {/* Learner Model - Visual Timeline */}
            <div className="profile-card">
              <div className="card-header">
                <span className="card-title">Learning Style Over Time</span>
              </div>
              <p className="summary-text" style={{ marginBottom: 16 }}>
                How your profile dimensions have evolved across {data.learner_model?.pacing_preference?.length || 0} checkpoints.
              </p>
              
              {data.learner_model && (
                <div className="trajectory-timelines">
                  {/* Curiosity Type */}
                  {data.learner_model.curiosity_type && data.learner_model.curiosity_type.length > 0 && (
                    <div className="trajectory-dimension">
                      <div className="dimension-header">
                        <div className="dimension-label">
                          <span className="dimension-icon">🔮</span>
                          <span>Curiosity Type</span>
                        </div>
                        <span className="dimension-current">{data.learner_model.curiosity_type[data.learner_model.curiosity_type.length - 1] || 'unknown'}</span>
                      </div>
                      <div className="dimension-timeline">
                        {data.learner_model.curiosity_type.map((v: any, idx: number) => (
                          <div key={idx} className="timeline-checkpoint">
                            <div className={`checkpoint-dot ${v ? 'filled' : 'empty'}`} title={`${v || 'unknown'}`} />
                            <span className="checkpoint-label">T{idx}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Pacing */}
                  {data.learner_model.pacing_preference && data.learner_model.pacing_preference.length > 0 && (
                    <div className="trajectory-dimension">
                      <div className="dimension-header">
                        <div className="dimension-label">
                          <span className="dimension-icon">⚡</span>
                          <span>Pacing</span>
                        </div>
                        <span className="dimension-current">{data.learner_model.pacing_preference[data.learner_model.pacing_preference.length - 1] || 'unknown'}</span>
                      </div>
                      <div className="dimension-timeline">
                        {data.learner_model.pacing_preference.map((v: any, idx: number) => (
                          <div key={idx} className="timeline-checkpoint">
                            <div className={`checkpoint-dot ${v ? 'filled' : 'empty'}`} title={`${v || 'unknown'}`} />
                            <span className="checkpoint-label">T{idx}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Uncertainty Tolerance */}
                  {data.learner_model.uncertainty_tolerance && data.learner_model.uncertainty_tolerance.length > 0 && (
                    <div className="trajectory-dimension">
                      <div className="dimension-header">
                        <div className="dimension-label">
                          <span className="dimension-icon">🌊</span>
                          <span>Uncertainty Tolerance</span>
                        </div>
                        <span className="dimension-current">{data.learner_model.uncertainty_tolerance[data.learner_model.uncertainty_tolerance.length - 1] || 'unknown'}</span>
                      </div>
                      <div className="dimension-timeline">
                        {data.learner_model.uncertainty_tolerance.map((v: any, idx: number) => (
                          <div key={idx} className="timeline-checkpoint">
                            <div className={`checkpoint-dot ${v ? 'filled' : 'empty'}`} title={`${v || 'unknown'}`} />
                            <span className="checkpoint-label">T{idx}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Entry Mode */}
                  {data.learner_model.entry_mode && data.learner_model.entry_mode.length > 0 && (
                    <div className="trajectory-dimension">
                      <div className="dimension-header">
                        <div className="dimension-label">
                          <span className="dimension-icon">💡</span>
                          <span>Entry Mode</span>
                        </div>
                        <span className="dimension-current">
                          {(() => {
                            const latest = data.learner_model.entry_mode[data.learner_model.entry_mode.length - 1]
                            if (!latest) return 'unknown'
                            const max = Math.max(latest.people || 0, latest.problems || 0, latest.ideas || 0)
                            if (latest.ideas === max) return 'Ideas-driven'
                            if (latest.people === max) return 'People-oriented'
                            if (latest.problems === max) return 'Problem-solving'
                            return 'unknown'
                          })()}
                        </span>
                      </div>
                      <div className="dimension-timeline">
                        {data.learner_model.entry_mode.map((v: any, idx: number) => (
                          <div key={idx} className="timeline-checkpoint">
                            <div className={`checkpoint-dot ${v && (v.people || v.problems || v.ideas) ? 'filled' : 'empty'}`} 
                                 title={`Ideas:${(v?.ideas || 0).toFixed(1)} People:${(v?.people || 0).toFixed(1)} Problems:${(v?.problems || 0).toFixed(1)}`} />
                            <span className="checkpoint-label">T{idx}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}


