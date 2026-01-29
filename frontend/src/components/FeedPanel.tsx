import { useState, useCallback, useEffect, useRef } from 'react'
import { api } from '../services/api'
import { stripMarkdown } from '../utils/textUtils'

interface FeedItem {
  id: number
  title: string
  content: string
  source_citation?: string
  source_url?: string
  source_type?: 'video' | 'article' | 'paper' | 'blog' | 'course' | 'tweet' | 'discussion' | 'general'
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

function getHostname(url: string): string {
  try {
    return new URL(url).hostname.replace('www.', '')
  } catch {
    return url.length > 40 ? url.slice(0, 40) + '...' : url
  }
}

function getSourceIcon(sourceType?: string) {
  switch (sourceType) {
    case 'video': return '🎬'
    case 'article': return '📰'
    case 'paper': return '📄'
    case 'blog': return '✍️'
    case 'course': return '🎓'
    case 'tweet': return '𝕏'
    case 'discussion': return '💬'
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
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [justGenerated, setJustGenerated] = useState(false)
  const [hasEverLoaded, setHasEverLoaded] = useState(false)
  const [expandedVideo, setExpandedVideo] = useState<number | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [page, setPage] = useState(0)
  const abortRef = useRef<AbortController | null>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const scrollSentinelRef = useRef<HTMLDivElement>(null)

  const fetchFeedStream = useCallback(async (loadPage = 0, append = false, refresh = false) => {
    // Abort any in-flight request
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    if (append) {
      setLoadingMore(true)
    } else {
      setLoading(true)
      setError(null)
      setItems([])
      setPage(0)
    }

    try {
      const response = await fetch(api.streamFeedUrl(), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          context_type: contextType,
          goal_id: goalId,
          goal_text: goalText,
          teaching_candidate_id: teachingCandidateId,
          teaching_topic: teachingTopic,
          user_background: userBackground,
          goals_summary: goalsSummary,
          page: loadPage,
          refresh,
        }),
        signal: controller.signal,
      })

      if (!response.ok) throw new Error('Failed to load feed')
      if (!response.body) throw new Error('No response body')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const jsonStr = line.slice(6).trim()
          if (!jsonStr) continue

          try {
            const data = JSON.parse(jsonStr)

            // Status messages (no title = status/control message)
            if (data.done) {
              setJustGenerated(!data.cached)
              setHasMore(!!data.has_more)
              setLoading(false)
              setLoadingMore(false)
              setHasEverLoaded(true)
              continue
            }
            if (data.status) continue

            // Feed item
            if (data.title) {
              if (append) {
                setItems(prev => [...prev, data as FeedItem])
              } else {
                setItems(prev => [...prev, data as FeedItem])
              }
              setHasEverLoaded(true)
              // Once first item arrives, stop showing full skeleton
              setLoading(false)
            }
          } catch {
            // Skip malformed JSON
          }
        }
      }

      setLoading(false)
      setLoadingMore(false)
      setHasEverLoaded(true)
    } catch (err: any) {
      if (err.name === 'AbortError') return
      setError('Failed to load feed')
      if (!append) setItems([])
      setLoading(false)
      setLoadingMore(false)
    }
  }, [userId, contextType, goalId, goalText, teachingCandidateId, teachingTopic, userBackground, goalsSummary])

  useEffect(() => {
    return () => { abortRef.current?.abort() }
  }, [])

  const handleGenerate = () => {
    fetchFeedStream(0, false)
  }

  const handleRefresh = () => {
    fetchFeedStream(0, false, true)
  }

  const handleLoadMore = useCallback(() => {
    if (loadingMore || !hasMore) return
    const nextPage = page + 1
    setPage(nextPage)
    fetchFeedStream(nextPage, true)
  }, [loadingMore, hasMore, page, fetchFeedStream])

  // Infinite scroll: observe sentinel element at bottom
  useEffect(() => {
    if (!scrollSentinelRef.current || !hasMore) return
    const container = scrollContainerRef.current
    // Skip if container is hidden (display:none parent)
    if (container && container.offsetParent === null) return
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) handleLoadMore() },
      { root: container || null, rootMargin: '200px' }
    )
    observer.observe(scrollSentinelRef.current)
    return () => observer.disconnect()
  }, [hasMore, handleLoadMore, items.length])

  // Auto-load feed on mount with delay
  useEffect(() => {
    if (!hasEverLoaded && !loading) {
      const timer = setTimeout(() => { fetchFeedStream(0, false) }, 5000)
      return () => clearTimeout(timer)
    }
  }, [hasEverLoaded, loading, fetchFeedStream])

  // Auto-refresh when context changes (only if context actually changed to something new)
  const prevContextRef = useRef({ goalId, goalText, teachingTopic, teachingCandidateId })
  useEffect(() => {
    const prev = prevContextRef.current
    const changed = prev.goalId !== goalId || prev.goalText !== goalText ||
      prev.teachingTopic !== teachingTopic || prev.teachingCandidateId !== teachingCandidateId
    prevContextRef.current = { goalId, goalText, teachingTopic, teachingCandidateId }
    if (changed && hasEverLoaded && !loading) {
      setItems([])
      setHasEverLoaded(false)
      setPage(0)
      setHasMore(false)
      const timer = setTimeout(() => { fetchFeedStream(0, false) }, 2000)
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

  // Show skeletons while loading and no items yet
  const showSkeletons = loading && items.length === 0

  if (showSkeletons) {
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
            onClick={handleRefresh}
            className="feed-refresh-btn"
            disabled={loading}
            title="Refresh feed"
          >
            ↻
          </button>
        </div>
      </div>

      <div className="feed-items" ref={scrollContainerRef}>
        {items.length === 0 ? (
          <div className="feed-empty">
            <p>No items yet. Continue your conversation and refresh.</p>
            <button onClick={handleGenerate} className="feed-generate-btn">
              Generate Feed
            </button>
          </div>
        ) : (
          <>
            {items.map((item) => (
              <div key={item.id} className={`feed-item feed-item-${item.source_type || 'general'}`}>
                {/* Thumbnail for articles/blogs/papers */}
                {item.thumbnail_url && item.source_type !== 'video' && (
                  <div className="feed-item-thumbnail">
                    <img src={item.thumbnail_url} alt="" loading="lazy" onError={(e) => { (e.target as HTMLElement).parentElement!.style.display = 'none' }} />
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

                  {/* Video thumbnail */}
                  {item.source_type === 'video' && item.thumbnail_url && expandedVideo !== item.id && (
                    <div className="feed-item-thumbnail feed-video-thumb">
                      <img src={item.thumbnail_url} alt="" loading="lazy" onError={(e) => { (e.target as HTMLElement).parentElement!.style.display = 'none' }} />
                    </div>
                  )}

                  {(item.source_citation || item.source_url) && (
                    <div className="feed-item-source">
                      <span className="feed-source-icon">{getSourceIcon(item.source_type)}</span>
                      <span className="feed-source-text">
                        {item.source_url ? (
                          <a href={item.source_url} target="_blank" rel="noopener noreferrer">
                            {item.source_citation && !item.source_citation.startsWith('http')
                              ? item.source_citation
                              : getHostname(item.source_url)}
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
            ))}
            {/* Show trailing skeletons while loading more */}
            {(loading || loadingMore) && (
              <>
                <SkeletonCard />
                <SkeletonCard />
              </>
            )}
            {/* Infinite scroll sentinel */}
            {hasMore && !loadingMore && (
              <div ref={scrollSentinelRef} style={{ height: 1 }} />
            )}
          </>
        )}
      </div>
    </div>
  )
}
