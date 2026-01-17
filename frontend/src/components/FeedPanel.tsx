import { useState, useCallback } from 'react'
import { api } from '../services/api'

interface FeedItem {
  id: number
  title: string
  content: string
  source_citation?: string
  source_url?: string
  relevance_note?: string
}

interface FeedPanelProps {
  userId: string
  contextType: 'exploration' | 'goal' | 'teaching_candidate'
  goalId?: number
  goalText?: string
  teachingCandidateId?: string
  teachingTopic?: string
  userBackground?: string
  goalsSummary?: string  // For exploration - summary of all goals
}

export default function FeedPanel({
  userId,
  contextType,
  goalId,
  goalText,
  teachingCandidateId,
  teachingTopic,
  userBackground,
  goalsSummary
}: FeedPanelProps) {
  const [items, setItems] = useState<FeedItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [justGenerated, setJustGenerated] = useState(false)
  const [hasEverLoaded, setHasEverLoaded] = useState(false)

  const fetchFeed = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await api.getFeed({
        user_id: userId,
        context_type: contextType,
        goal_id: goalId,
        goal_text: goalText,
        teaching_candidate_id: teachingCandidateId,
        teaching_topic: teachingTopic,
        user_background: userBackground,
        goals_summary: goalsSummary
      })

      setItems(response.items)
      setJustGenerated(response.generated)
      setHasEverLoaded(true)
    } catch (err) {
      console.error('[FeedPanel] Error fetching feed:', err)
      setError('Failed to load feed')
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [userId, contextType, goalId, goalText, teachingCandidateId, teachingTopic, userBackground, goalsSummary])

  const handleGenerate = () => {
    fetchFeed()
  }

  const getContextLabel = () => {
    switch (contextType) {
      case 'exploration':
        return 'Explore & Learn'
      case 'goal':
        return goalText ? `About: ${goalText.slice(0, 40)}...` : 'Learning Goal'
      case 'teaching_candidate':
        return teachingTopic ? `Deep Dive: ${teachingTopic.slice(0, 30)}...` : 'Topic Focus'
      default:
        return 'Related Content'
    }
  }

  // Loading state
  if (loading) {
    return (
      <div className="feed-panel">
        <div className="feed-header">
          <h3>📚 {getContextLabel()}</h3>
        </div>
        <div className="feed-loading">
          <div className="feed-loading-spinner" />
          <p>Curating relevant content...</p>
        </div>
      </div>
    )
  }

  // Error state
  if (error) {
    return (
      <div className="feed-panel">
        <div className="feed-header">
          <h3>📚 {getContextLabel()}</h3>
        </div>
        <div className="feed-error">
          <p>{error}</p>
          <button onClick={handleGenerate} className="feed-generate-btn">
            Try Again
          </button>
        </div>
      </div>
    )
  }

  // Initial state - not yet loaded
  if (!hasEverLoaded) {
    return (
      <div className="feed-panel">
        <div className="feed-header">
          <h3>📚 {getContextLabel()}</h3>
        </div>
        <div className="feed-empty">
          <p>Get personalized content based on your conversation.</p>
          <button onClick={handleGenerate} className="feed-generate-btn">
            ✨ Generate Feed
          </button>
        </div>
      </div>
    )
  }

  // Loaded state with items
  return (
    <div className="feed-panel">
      <div className="feed-header">
        <h3>📚 {getContextLabel()}</h3>
        <div className="feed-header-actions">
          {justGenerated && (
            <span className="feed-new-badge">New</span>
          )}
          <button
            onClick={handleGenerate}
            className="feed-refresh-btn"
            disabled={loading}
            title="Refresh feed"
          >
            ↻
          </button>
        </div>
      </div>
      
      <div className="feed-items">
        {items.length === 0 ? (
          <div className="feed-empty">
            <p>No items yet. Continue your conversation and refresh.</p>
            <button onClick={handleGenerate} className="feed-generate-btn">
              ✨ Generate Feed
            </button>
          </div>
        ) : (
          items.map((item) => (
            <div key={item.id} className="feed-item">
              <h4 className="feed-item-title">{item.title}</h4>
              <p className="feed-item-content">{item.content}</p>
              {item.source_citation && (
                <div className="feed-item-source">
                  <span className="feed-source-icon">📖</span>
                  <span className="feed-source-text">{item.source_citation}</span>
                </div>
              )}
              {item.relevance_note && (
                <p className="feed-item-relevance">{item.relevance_note}</p>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
