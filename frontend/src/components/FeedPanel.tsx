import { useState, useCallback, useEffect } from 'react'
import { api } from '../services/api'
import { stripMarkdown } from '../utils/textUtils'

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

  // Auto-load feed on mount (only once) - delay to let opening question generate first
  useEffect(() => {
    if (!hasEverLoaded && !loading) {
      // Delay feed loading so the chat opening question can generate first
      // The user will be reading the question while feed loads in background
      const timer = setTimeout(() => {
        fetchFeed()
      }, 5000)  // 5 second delay
      return () => clearTimeout(timer)
    }
  }, [hasEverLoaded, loading, fetchFeed])

  // Auto-refresh when context changes (goal/teaching panel switches)
  useEffect(() => {
    // Auto-refresh when context changes significantly (goal text, teaching topic)
    // This triggers when the user switches panels or a new goal/teaching is created
    if (hasEverLoaded && !loading) {
      // Add a small delay to let the conversation context update
      const timer = setTimeout(() => {
        fetchFeed()
      }, 2000)
      return () => clearTimeout(timer)
    }
  }, [goalText, teachingTopic, goalId, teachingCandidateId])

  const getContextLabel = () => {
    switch (contextType) {
      case 'exploration':
        return 'Feed'
      case 'goal':
        return goalText ? `About: ${stripMarkdown(goalText).slice(0, 40)}...` : 'Learning Goal'
      case 'teaching_candidate':
        return teachingTopic ? `Deep Dive: ${stripMarkdown(teachingTopic).slice(0, 30)}...` : 'Topic Focus'
      default:
        return 'Related Content'
    }
  }

  // Loading state
  if (loading) {
    return (
      <div className="feed-panel">
        <div className="feed-header">
          <h3>{getContextLabel()}</h3>
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
          <h3>{getContextLabel()}</h3>
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

  // Initial state - not yet loaded (will auto-load after delay)
  if (!hasEverLoaded && !loading) {
    return (
      <div className="feed-panel">
        <div className="feed-header">
          <h3>{getContextLabel()}</h3>
        </div>
        <div className="feed-empty">
          <p>Content will load shortly...</p>
        </div>
      </div>
    )
  }

  // Loaded state with items
  return (
    <div className="feed-panel">
      <div className="feed-header">
        <h3>{getContextLabel()}</h3>
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
              <h4 className="feed-item-title">{stripMarkdown(item.title)}</h4>
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
