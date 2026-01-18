import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, LearnerTrajectoryDashboard, UserData } from '../services/api'
import { LineChart, Line, AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'

interface TrajectoryPanelProps {
  userId: string
}

export default function TrajectoryPanel({ userId }: TrajectoryPanelProps) {
  const [data, setData] = useState<LearnerTrajectoryDashboard | null>(null)
  const [userData, setUserData] = useState<UserData | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)

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
      const [d, u] = await Promise.all([
        api.refreshTrajectory(userId),
        api.getUserData(userId),
      ])
      setData(d)
      setUserData(u)
    } catch (e: any) {
      setError(e?.message || 'Failed to refresh trajectory')
    } finally {
      setIsLoading(false)
    }
  }, [userId])

  useEffect(() => {
    load()
  }, [load])

  type GraphNode = {
    id: string
    label: string
    type: 'root' | 'goal' | 'task'
    goalId?: number
    status?: string
    meta?: Record<string, any>
  }

  const graphNodes = useMemo<GraphNode[]>(() => {
    const nodes: GraphNode[] = []
    nodes.push({
      id: 'root',
      label: userData?.username ? `${userData.username}'s learning map` : 'Learning map',
      type: 'root',
    })

    const goals = userData?.goals || []
    goals.forEach((goal) => {
      const goalId = goal.id
      nodes.push({
        id: `goal-${goalId}`,
        label: goal.goal_text,
        type: 'goal',
        goalId,
        status: goal.status,
        meta: {
          momentum: (data?.goals || []).find(g => g.goal_id === goalId)?.momentum,
          learning_summary: (data?.goals || []).find(g => g.goal_id === goalId)?.learning_summary,
          next_suggested_move: (data?.goals || []).find(g => g.goal_id === goalId)?.next_suggested_move,
        },
      })

      const teachingCandidates = Array.isArray(goal.teaching_candidate)
        ? goal.teaching_candidate
        : (goal.teaching_candidate ? [goal.teaching_candidate] : [])

      teachingCandidates.forEach((tc: any, idx: number) => {
        const taskId = tc?.id ?? idx + 1
        nodes.push({
          id: `task-${goalId}-${taskId}`,
          label: tc?.topic || 'Unnamed task',
          type: 'task',
          goalId,
          status: tc?.status,
          meta: {
            identified_gap: tc?.identified_gap,
            focus_question: tc?.focus_question,
            justification: tc?.justification,
          },
        })
      })
    })

    return nodes
  }, [data?.goals, userData])

  const selectedNode = useMemo(() => {
    return graphNodes.find(n => n.id === selectedNodeId) || graphNodes[0]
  }, [graphNodes, selectedNodeId])

  const highlightsForGoal = useMemo(() => {
    if (!selectedNode || selectedNode.type !== 'goal' || !selectedNode.goalId) return []
    return (data?.highlights || []).filter(h => h.goal_id === selectedNode.goalId)
  }, [data?.highlights, selectedNode])

  // Transform learner_model data for Recharts
  const chartData = useMemo(() => {
    if (!data?.learner_model) return []
    
    const maxLen = Math.max(
      data.learner_model.curiosity_type?.length || 0,
      data.learner_model.pacing_preference?.length || 0,
      data.learner_model.uncertainty_tolerance?.length || 0,
      data.learner_model.entry_mode?.length || 0
    )
    
    return Array.from({ length: maxLen }, (_, idx) => {
      const curiosity = data.learner_model.curiosity_type?.[idx]
      const pacing = data.learner_model.pacing_preference?.[idx]
      const uncertainty = data.learner_model.uncertainty_tolerance?.[idx]
      const entry = data.learner_model.entry_mode?.[idx]
      
      return {
        checkpoint: `T${idx}`,
        curiosity: curiosity === 'interest' ? 2 : curiosity === 'deprivation' ? 1 : curiosity === 'mixed' ? 1.5 : 0,
        pacing: pacing === 'fast_resolution' ? 2 : pacing === 'exploratory' ? 1 : pacing === 'mixed' ? 1.5 : 0,
        uncertainty: uncertainty === 'high' ? 3 : uncertainty === 'medium' ? 2 : uncertainty === 'low' ? 1 : 0,
        ideas: entry?.ideas || 0,
        people: entry?.people || 0,
        problems: entry?.problems || 0,
      }
    })
  }, [data?.learner_model])

  // Generate narrative descriptions of changes
  const narrativeInsights = useMemo(() => {
    if (!data?.learner_model || chartData.length < 2) return []
    
    const insights: string[] = []
    const lm = data.learner_model
    
    if (lm.curiosity_type && lm.curiosity_type.length > 1) {
      const first = lm.curiosity_type[0]
      const last = lm.curiosity_type[lm.curiosity_type.length - 1]
      if (first !== last) {
        insights.push(`Your curiosity shifted from ${first || 'undefined'} to ${last} over time.`)
      }
    }
    
    if (lm.uncertainty_tolerance && lm.uncertainty_tolerance.length > 1) {
      const first = lm.uncertainty_tolerance[0]
      const last = lm.uncertainty_tolerance[lm.uncertainty_tolerance.length - 1]
      if (first !== last) {
        const direction = last === 'high' ? 'more' : last === 'low' ? 'less' : 'somewhat'
        insights.push(`You've become ${direction} comfortable with uncertainty.`)
      }
    }
    
    if (lm.entry_mode && lm.entry_mode.length > 1) {
      const first = lm.entry_mode[0]
      const last = lm.entry_mode[lm.entry_mode.length - 1]
      if (first && last) {
        const firstDom = first.ideas > first.people && first.ideas > first.problems ? 'ideas' :
                        first.people > first.problems ? 'people' : 'problems'
        const lastDom = last.ideas > last.people && last.ideas > last.problems ? 'ideas' :
                       last.people > last.problems ? 'people' : 'problems'
        if (firstDom !== lastDom) {
          insights.push(`Your approach evolved from ${firstDom}-focused to ${lastDom}-focused.`)
        }
      }
    }
    
    return insights
  }, [data?.learner_model, chartData])

  return (
    <div className="trajectory-panel">
      <div className="trajectory-panel-header">
        <h2>Learner Trajectory</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {data?.updated_at && <span className="turn-counter">Updated</span>}
          <button className="refresh-btn" onClick={refresh} disabled={isLoading} title="Refresh trajectory">
            {isLoading ? '...' : '↻'}
          </button>
        </div>
      </div>

      <div className="trajectory-panel-content">
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
            <div className="trajectory-grid">
              {/* Left: Graph */}
              <div className="trajectory-graph">
                <div className="profile-card">
                  <div className="card-header">
                    <span className="card-title">Learning Graph</span>
                    <span className="item-count">{graphNodes.length - 1}</span>
                  </div>
                  <div className="graph-tree">
                    {graphNodes.map((node) => (
                      <button
                        key={node.id}
                        className={`graph-node ${node.type} ${selectedNode?.id === node.id ? 'active' : ''}`}
                        onClick={() => setSelectedNodeId(node.id)}
                        title={node.label}
                      >
                        <span className="graph-node-label">{node.label}</span>
                        {node.status && <span className={`graph-node-status ${node.status}`}>{node.status}</span>}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Right: Node-specific metrics */}
              <div className="trajectory-details">
                <div className="profile-card summary-card">
                  <div className="card-header">
                    <span className="card-title">Selection</span>
                    <span className="readiness-badge medium">{selectedNode?.type || 'root'}</span>
                  </div>
                  <p className="summary-text">{selectedNode?.label || 'Learning map'}</p>
                  {selectedNode?.type === 'root' && data.insights && (
                    <p className="summary-text">{data.insights}</p>
                  )}
                </div>

                {selectedNode?.type === 'goal' && (
                  <div className="profile-card">
                    <div className="card-header">
                      <span className="card-title">Goal Metrics</span>
                    </div>
                    <p className="summary-text">Status: {selectedNode.status || 'unknown'}</p>
                    {selectedNode.meta?.momentum && (
                      <p className="summary-text">Momentum: {selectedNode.meta.momentum}</p>
                    )}
                    {selectedNode.meta?.learning_summary && (
                      <p className="summary-text">{selectedNode.meta.learning_summary}</p>
                    )}
                    {selectedNode.meta?.next_suggested_move && (
                      <p className="summary-text">Next: {selectedNode.meta.next_suggested_move}</p>
                    )}
                  </div>
                )}

                {selectedNode?.type === 'task' && (
                  <div className="profile-card">
                    <div className="card-header">
                      <span className="card-title">Task Metrics</span>
                    </div>
                    {selectedNode.status && (
                      <p className="summary-text">Status: {selectedNode.status}</p>
                    )}
                    {selectedNode.meta?.focus_question && (
                      <p className="summary-text">Focus question: {selectedNode.meta.focus_question}</p>
                    )}
                    {selectedNode.meta?.identified_gap && (
                      <p className="summary-text">Gap: {selectedNode.meta.identified_gap}</p>
                    )}
                    {selectedNode.meta?.justification && (
                      <p className="summary-text">Justification: {selectedNode.meta.justification}</p>
                    )}
                  </div>
                )}

                {/* Highlights filtered by goal */}
                {selectedNode?.type === 'goal' && (
                  <div className="profile-card">
                    <div className="card-header">
                      <span className="card-title">Highlights for Goal</span>
                      <span className="item-count">{highlightsForGoal.length}</span>
                    </div>
                    {highlightsForGoal.length === 0 && (
                      <p className="summary-text">No highlights yet for this goal.</p>
                    )}
                    <div className="open-questions-list">
                      {highlightsForGoal.slice().reverse().slice(0, 8).map((h, idx) => (
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
                )}

                {/* Learning Style Over Time - Visual Charts */}
                {chartData.length > 0 && (
                  <div className="profile-card">
                    <div className="card-header">
                      <span className="card-title">Learning Style Evolution</span>
                      <span className="item-count">{chartData.length} checkpoints</span>
                    </div>
                    
                    {/* Narrative Insights */}
                    {narrativeInsights.length > 0 && (
                      <div className="trajectory-narratives">
                        {narrativeInsights.map((insight, idx) => (
                          <p key={idx} className="narrative-insight">{insight}</p>
                        ))}
                      </div>
                    )}
                    
                    {/* Curiosity & Pacing Chart */}
                    <div className="chart-section">
                      <h4 className="chart-title">Curiosity & Pacing Trends</h4>
                      <ResponsiveContainer width="100%" height={180}>
                        <LineChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                          <XAxis dataKey="checkpoint" tick={{ fontSize: 11 }} />
                          <YAxis domain={[0, 3]} tick={{ fontSize: 11 }} />
                          <Tooltip />
                          <Legend wrapperStyle={{ fontSize: 11 }} />
                          <Line 
                            type="monotone" 
                            dataKey="curiosity" 
                            stroke="#8b5cf6" 
                            strokeWidth={2}
                            name="Curiosity"
                            dot={{ fill: '#8b5cf6', r: 4 }}
                          />
                          <Line 
                            type="monotone" 
                            dataKey="pacing" 
                            stroke="#f59e0b" 
                            strokeWidth={2}
                            name="Pacing"
                            dot={{ fill: '#f59e0b', r: 4 }}
                          />
                          <Line 
                            type="monotone" 
                            dataKey="uncertainty" 
                            stroke="#06b6d4" 
                            strokeWidth={2}
                            name="Uncertainty Tolerance"
                            dot={{ fill: '#06b6d4', r: 4 }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                    
                    {/* Entry Mode Stacked Area Chart */}
                    <div className="chart-section">
                      <h4 className="chart-title">Entry Mode Distribution</h4>
                      <ResponsiveContainer width="100%" height={180}>
                        <AreaChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                          <XAxis dataKey="checkpoint" tick={{ fontSize: 11 }} />
                          <YAxis domain={[0, 1]} tick={{ fontSize: 11 }} />
                          <Tooltip />
                          <Legend wrapperStyle={{ fontSize: 11 }} />
                          <Area 
                            type="monotone" 
                            dataKey="ideas" 
                            stackId="1"
                            stroke="#3b82f6" 
                            fill="#93c5fd"
                            name="Ideas"
                          />
                          <Area 
                            type="monotone" 
                            dataKey="people" 
                            stackId="1"
                            stroke="#10b981" 
                            fill="#6ee7b7"
                            name="People"
                          />
                          <Area 
                            type="monotone" 
                            dataKey="problems" 
                            stackId="1"
                            stroke="#f97316" 
                            fill="#fdba74"
                            name="Problems"
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}
                
                {/* Fallback if no chart data */}
                {chartData.length === 0 && (
                  <div className="profile-card">
                    <div className="card-header">
                      <span className="card-title">Learning Style Over Time</span>
                    </div>
                    <p className="summary-text">
                      No learning style data available yet. Continue exploring to build your profile.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}


