import { useState, useCallback, useEffect, useRef } from 'react'
import { api } from '../services/api'
import { stripMarkdown } from '../utils/textUtils'

interface FeedItem {
  id: number
  title: string
  content: string
  source_citation?: string
  source_url?: string
  source_type?: 'video' | 'article' | 'paper' | 'blog' | 'course' | 'general'
  thumbnail_url?: string
  embed_url?: string
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
  goalsSummary?: string
}

function LazyVideoEmbed({ embedUrl, title }: { embedUrl: string; title: string }) {
  const [loaded, setLoaded] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current) return
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setLoaded(true) },
      { rootMargin: '100px' }
    )
    observer.observe(ref.current)
    return () => observer.disconnect()
  }, [])

  return (
    <div ref={ref} className="feed-video-embed">
      {loaded ? (
        <iframe
          src={embedUrl}
          title={title}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          loading="lazy"
        />
      ) : (
        <div className="feed-video-placeholder">
          <span className="feed-video-play-icon">▶</span>
        </div>
      )}
    </div>
  )
}

function SkeletonCard() {
  return (
    <div className="feed-item feed-skeleton">
      <div className="skeleton-line skeleton-title" />
      <div className="skeleton-line skeleton-text" />
      <div className="skeleton-line skeleton-text short" />
      <div className="skeleton-line skeleton-source" />
    </div>
  )
}

function getSourceIcon(sourceType?: string) {
  switch (sourceType) {
    case 'video': return '🎬'
    case 'article': return '📰'
    case 'paper': return '📄'
    case 'blog': return '✍️'
    case 'course': return '🎓'
    default: return '📖'
  }
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
  const [expandedVideo, setExpandedVideo] = useState<number | null>(null)

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
    } catch (_) {
      setError('Failed to load feed')
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [userId, contextType, goalId, goalText, teachingCandidateId, teachingTopic, userBackground, goalsSummary])

  const handleGenerate = () => {
    fetchFeed()
  }

  // Auto-load feed on mount with delay
  useEffect(() => {
    if (!hasEverLoaded && !loading) {
      const timer = setTimeout(() => { fetchFeed() }, 5000)
      return () => clearTimeout(timer)
    }
  }, [hasEverLoaded, loading, fetchFeed])

  // Auto-refresh when context changes
  useEffect(() => {
    if (hasEverLoaded && !loading) {
      const timer = setTimeout(() => { fetchFeed() }, 2000)
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
        return teachingTopic ? `Focus: ${stripMarkdown(teachingTopic).slice(0, 30)}...` : 'Topic Focus'
      default:
        return 'Related Content'
    }
  }

  // Skeleton loading state
  if (loading) {
    return (
      <div className="feed-panel">
        <div className="feed-header">
          <h3>{getContextLabel()}</h3>
        </div>
        <div className="feed-items">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      </div>
    )
  }

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

  if (!hasEverLoaded && !loading) {
    return (
      <div className="feed-panel">
        <div className="feed-header">
          <h3>{getContextLabel()}</h3>
        </div>
        <div className="feed-items">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      </div>
    )
  }

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
              Generate Feed
            </button>
          </div>
        ) : (
          items.map((item) => (
            <div key={item.id} className={`feed-item feed-item-${item.source_type || 'general'}`}>
              {/* Thumbnail for articles/blogs/papers */}
              {item.thumbnail_url && item.source_type !== 'video' && (
                <div className="feed-item-thumbnail">
                  <img src={item.thumbnail_url} alt="" loading="lazy" />
                </div>
              )}

              <div className="feed-item-body">
                <div className="feed-item-type-badge">
                  <span>{getSourceIcon(item.source_type)}</span>
                  <span className="feed-type-label">{item.source_type || 'resource'}</span>
                </div>

                <h4 className="feed-item-title">
                  {item.source_url ? (
                    <a href={item.source_url} target="_blank" rel="noopener noreferrer">
                      {stripMarkdown(item.title)}
                    </a>
                  ) : (
                    stripMarkdown(item.title)
                  )}
                </h4>

                <p className="feed-item-content">{item.content}</p>

                {/* Video embed */}
                {item.source_type === 'video' && item.embed_url && (
                  <>
                    {expandedVideo === item.id ? (
                      <LazyVideoEmbed embedUrl={item.embed_url} title={item.title} />
                    ) : (
                      <button
                        className="feed-play-btn"
                        onClick={() => setExpandedVideo(item.id)}
                      >
                        ▶ Watch Video
                      </button>
                    )}
                  </>
                )}

                {item.source_citation && (
                  <div className="feed-item-source">
                    <span className="feed-source-icon">{getSourceIcon(item.source_type)}</span>
                    <span className="feed-source-text">
                      {item.source_url ? (
                        <a href={item.source_url} target="_blank" rel="noopener noreferrer">
                          {item.source_citation}
                        </a>
                      ) : (
                        item.source_citation
                      )}
                    </span>
                  </div>
                )}

                {item.relevance_note && (
                  <p className="feed-item-relevance">{item.relevance_note}</p>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
