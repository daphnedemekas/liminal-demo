import { useState, useEffect } from 'react'
import { api, ContextItem } from '../services/api'
import { getApiBaseUrl } from '../config'

interface ContextTabProps {
  goalId: number
  userId: string
}

export default function ContextTab({ goalId, userId }: ContextTabProps) {
  const [contexts, setContexts] = useState<ContextItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [newContextText, setNewContextText] = useState('')
  const [isAdding, setIsAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadContexts = async () => {
    try {
      setIsLoading(true)
      setError(null)
      const items = await api.getContexts(goalId)
      setContexts(items.filter(item => item.is_active))
    } catch (err: any) {
      console.error('[ContextTab] Failed to load contexts:', err)
      setError(err.message || 'Failed to load contexts')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadContexts()
  }, [goalId])

  // Reload contexts when tab becomes visible (in case they were updated elsewhere)
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (!document.hidden) {
        loadContexts()
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [])

  const handleAdd = async () => {
    if (!newContextText.trim() || isAdding) return

    try {
      setIsAdding(true)
      setError(null)
      const newItem = await api.addContext(goalId, userId, newContextText.trim(), 'text')
      setContexts(prev => [newItem, ...prev])
      setNewContextText('')
    } catch (err: any) {
      console.error('[ContextTab] Failed to add context:', err)
      setError(err.message || 'Failed to add context')
    } finally {
      setIsAdding(false)
    }
  }

  const handleDelete = async (contextId: number) => {
    if (!confirm('Delete this context item?')) return

    try {
      await api.deleteContext(goalId, contextId)
      setContexts(prev => prev.filter(item => item.id !== contextId))
    } catch (err: any) {
      console.error('[ContextTab] Failed to delete context:', err)
      setError(err.message || 'Failed to delete context')
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      handleAdd()
    }
  }

  return (
    <div className="panel-tab context-tab">
      <div className="panel-tab-header">
        <h3>Context</h3>
        <button onClick={loadContexts} className="refresh-btn" title="Refresh">
          ↻
        </button>
      </div>

      {error && (
        <div className="panel-error">
          {error}
        </div>
      )}

      <div className="panel-tab-content">
        {/* Add Context Form */}
        <div className="context-add-form">
          <textarea
            className="context-textarea"
            value={newContextText}
            onChange={(e) => setNewContextText(e.target.value)}
            onKeyDown={handleKeyPress}
            placeholder="Add context (text, notes, code snippets, etc.)...&#10;Press Cmd/Ctrl+Enter to add"
            rows={4}
            disabled={isAdding}
          />
          <button
            className="context-add-btn"
            onClick={handleAdd}
            disabled={!newContextText.trim() || isAdding}
          >
            {isAdding ? 'Adding...' : 'Add Context'}
          </button>
        </div>

        {/* Context List */}
        {isLoading ? (
          <div className="panel-loading">Loading contexts...</div>
        ) : contexts.length === 0 ? (
          <div className="panel-empty">
            <p>No context items yet.</p>
            <p className="panel-empty-hint">Add text, notes, or code snippets to help the AI understand your goal better.</p>
          </div>
        ) : (
          <div className="context-list">
            {contexts.map((item) => (
              <div key={item.id} className="context-item">
                <div className="context-item-header">
                  <span className="context-type-badge">{item.content_type}</span>
                  <span className="context-date">
                    {item.created_at ? new Date(item.created_at).toLocaleDateString() : ''}
                  </span>
                  <button
                    className="context-delete-btn"
                    onClick={() => handleDelete(item.id)}
                    title="Delete"
                  >
                    ×
                  </button>
                </div>
                <div className="context-item-content">
                  {item.text_content || item.file_name || 'No content'}
                </div>
                {item.token_count > 0 && (
                  <div className="context-item-meta">
                    ~{item.token_count} tokens
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

