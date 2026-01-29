import { useState, useEffect, useRef, useCallback } from 'react'
import { api, DocumentItem } from '../services/api'
import { getApiBaseUrl } from '../config'
import RichTextEditor from './RichTextEditor'

interface DraftTabProps {
  goalId: number
  userId: string
  onSendToChat?: (message: string) => void
}

interface DocumentSuggestion {
  suggestion_type: string
  text: string
  location?: string
  confidence: number
}

export default function DraftTab({ goalId, userId, onSendToChat }: DraftTabProps) {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [activeDocument, setActiveDocument] = useState<DocumentItem | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isCreating, setIsCreating] = useState(false)
  const [newDocTitle, setNewDocTitle] = useState('')
  const [suggestions, setSuggestions] = useState<DocumentSuggestion[]>([])
  const [isGeneratingSuggestions, setIsGeneratingSuggestions] = useState(false)
  const [isExpandingSuggestion, setIsExpandingSuggestion] = useState(false)
  const [expandedSuggestionId, setExpandedSuggestionId] = useState<string | null>(null)
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const lastSavedContentRef = useRef<string>('')
  const lastKnownVersionRef = useRef<number>(0)

  const loadDocuments = async () => {
    try {
      setIsLoading(true)
      setError(null)
      const items = await api.getDocuments(goalId)
      const activeItems = items.filter(item => item.is_active)
      setDocuments(activeItems)
      
      // Auto-select first document if available and none selected
      // Or restore the last active document if it still exists
      if (activeItems.length > 0) {
        if (activeDocument && activeItems.find(d => d.id === activeDocument.id)) {
          // Reload the active document to get latest version
          const refreshed = await api.getDocument(activeDocument.id)
          setActiveDocument(refreshed)
          lastKnownVersionRef.current = refreshed.version
          lastSavedContentRef.current = refreshed.plain_text || ''
        } else {
          // Select first document
          setActiveDocument(activeItems[0])
          lastKnownVersionRef.current = activeItems[0].version
          lastSavedContentRef.current = activeItems[0].plain_text || ''
        }
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load documents')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadDocuments()
    
    // Ensure goal panels are initialized (creates default channels if needed)
    const initPanels = async () => {
      try {
        const apiUrl = getApiBaseUrl()
        await fetch(`${apiUrl}/api/goal/${goalId}/panels/init?user_id=${userId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        })
      } catch (err) {
        // Not critical - panels may already exist
      }
    }
    initPanels()
  }, [goalId, userId])

  // Save function that can be called directly
  const saveDocument = useCallback(async (doc: DocumentItem | null, content?: string): Promise<boolean> => {
    if (!doc) return false

    const contentToSave = content !== undefined ? content : doc.plain_text
    // Skip save if content hasn't changed
    if (contentToSave === lastSavedContentRef.current) return true
    try {
      const updated = await api.updateDocument(doc.id, { plain_text: contentToSave })
      lastKnownVersionRef.current = updated.version
      setActiveDocument(prev => prev?.id === doc.id ? updated : prev)
      lastSavedContentRef.current = contentToSave || ''
      return true
    } catch (err: any) {
      setError(err.message || 'Failed to save document')
      return false
    }
  }, [])

  // Connect to document WebSocket for AI suggestions
  useEffect(() => {
    if (!activeDocument) {
      // Close existing connection
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      return
    }

    const apiUrl = getApiBaseUrl().replace(/^http/, 'ws')
    const ws = new WebSocket(`${apiUrl}/ws/document/${activeDocument.id}`)

    ws.onopen = () => {
      setError(null)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        
        if (data.type === 'suggestions') {
          const suggestionsList = Array.isArray(data.suggestions) ? data.suggestions : []
          setSuggestions(suggestionsList)
          setIsGeneratingSuggestions(false)
          if (suggestionsList.length === 0) {
            setError('No suggestions generated. Try writing more content (at least 20 characters).')
          } else {
            setError(null)
          }
        } else if (data.type === 'sync_ack') {
        } else if (data.type === 'error') {
          setError(data.message || 'Error generating suggestions')
          setIsGeneratingSuggestions(false)
        } else {
        }
      } catch (err) {
        setError('Failed to parse server response')
        setIsGeneratingSuggestions(false)
      }
    }

    ws.onerror = () => {
      setError('Failed to connect to document service. Check backend logs.')
      setIsGeneratingSuggestions(false)
    }

    ws.onclose = (event) => {
      if (event.code !== 1000) { // Not a normal closure
        setError('Connection closed unexpectedly')
      }
    }

    wsRef.current = ws

    return () => {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [activeDocument?.id])

  // Auto-save on content change (debounced) and trigger suggestions
  const handleContentChange = (plainText: string, jsonContent?: object) => {
    if (!activeDocument) return

    // Update local state immediately
    setActiveDocument(prev => prev ? { ...prev, plain_text: plainText, content: jsonContent || prev.content } : null)
    const content = plainText

    // Clear existing timeout
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current)
    }

    // Set new timeout for auto-save (3 seconds after last change)
    saveTimeoutRef.current = setTimeout(async () => {
      if (activeDocument) {
        setIsSaving(true)
        const saved = await saveDocument(activeDocument, content)
        setIsSaving(false)

        // Only trigger AI suggestions if content was actually saved (changed)
        if (saved && wsRef.current && wsRef.current.readyState === WebSocket.OPEN && content.trim().length >= 20) {
          setIsGeneratingSuggestions(true)
          wsRef.current.send(JSON.stringify({
            type: 'update',
            plain_text: content,
            content: {}
          }))
        }
      }
    }, 3000)
  }

  // Handle clicking on a suggestion to expand it in chat
  const handleSuggestionClick = async (suggestion: DocumentSuggestion, index: number) => {
    if (!activeDocument || !onSendToChat) {
      setError('Cannot send to chat - chat not available')
      return
    }

    // Prevent multiple clicks - check if already expanding or this suggestion was already expanded
    const suggestionId = `${suggestion.suggestion_type}-${suggestion.text.substring(0, 50)}-${index}`
    if (isExpandingSuggestion || expandedSuggestionId === suggestionId) {
      return
    }

    try {
      setIsExpandingSuggestion(true)
      setExpandedSuggestionId(suggestionId)
      setError(null)
      
      // Call backend to expand the suggestion
      const apiUrl = getApiBaseUrl()
      const response = await fetch(`${apiUrl}/api/document/${activeDocument.id}/expand-suggestion`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          suggestion: {
            suggestion_type: suggestion.suggestion_type,
            text: suggestion.text,
            location: suggestion.location
          },
          document_content: activeDocument.plain_text,
          goal_id: goalId
        })
      })

      if (!response.ok) {
        throw new Error(`Failed to expand suggestion: ${response.statusText}`)
      }

      const data = await response.json()
      const expandedMessage = data.expanded_message

      // Send the expanded message to chat (only once)
      onSendToChat(expandedMessage)
      
    } catch (err: any) {
      setError(err.message || 'Failed to expand suggestion')
      // Reset on error so user can retry
      setExpandedSuggestionId(null)
    } finally {
      setIsExpandingSuggestion(false)
    }
  }

  // Request suggestions manually
  const requestSuggestions = useCallback(() => {
    if (!activeDocument) {
      setError('No document selected')
      return
    }
    
    const currentContent = activeDocument.plain_text || ''
    if (!currentContent || currentContent.trim().length < 20) {
      setError('Document needs at least 20 characters for AI analysis')
      return
    }
    
    const sendRequest = () => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        setError('Connection failed. Please try again.')
        setIsGeneratingSuggestions(false)
        return
      }
      try {
        wsRef.current.send(JSON.stringify({
          type: 'request_suggestion',
          selection: '' // Empty means analyze entire document
        }))
      } catch {
        setError('Failed to send request. Please try again.')
        setIsGeneratingSuggestions(false)
      }
    }

    setIsGeneratingSuggestions(true)
    setError(null)
    setSuggestions([]) // Clear old suggestions

    // If WebSocket isn't open, reconnect and send once connected
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      if (wsRef.current) {
        // Suppress error from intentional close
        wsRef.current.onclose = null
        wsRef.current.onerror = null
        wsRef.current.close()
      }
      const apiUrl = getApiBaseUrl().replace(/^http/, 'ws')
      const ws = new WebSocket(`${apiUrl}/ws/document/${activeDocument.id}`)
      ws.onopen = () => {
        setError(null)
        sendRequest()
      }
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'suggestions') {
            const suggestionsList = Array.isArray(data.suggestions) ? data.suggestions : []
            setSuggestions(suggestionsList)
            setIsGeneratingSuggestions(false)
            if (suggestionsList.length === 0) {
              setError('No suggestions generated. Try writing more content.')
            } else {
              setError(null)
            }
          } else if (data.type === 'error') {
            setError(data.message || 'Error generating suggestions')
            setIsGeneratingSuggestions(false)
          }
        } catch {
          setError('Failed to parse server response')
          setIsGeneratingSuggestions(false)
        }
      }
      ws.onerror = () => {
        setError('Failed to connect to document service.')
        setIsGeneratingSuggestions(false)
      }
      ws.onclose = (event) => {
        if (event.code !== 1000) {
          setError('Connection closed unexpectedly')
        }
      }
      wsRef.current = ws
    } else {
      sendRequest()
    }

    // Timeout after 30 seconds
    const timeoutId = setTimeout(() => {
      setIsGeneratingSuggestions(prev => {
        if (prev) {
          setError('Suggestion generation timed out. Please try again.')
          return false
        }
        return prev
      })
    }, 30000)
    return () => clearTimeout(timeoutId)
  }, [activeDocument])

  // Save on blur (immediate save when user leaves textarea)
  const handleBlur = async () => {
    if (activeDocument && saveTimeoutRef.current) {
      // Clear the debounced save and save immediately
      clearTimeout(saveTimeoutRef.current)
      saveTimeoutRef.current = null
      setIsSaving(true)
      await saveDocument(activeDocument)
      setIsSaving(false)
    }
  }

  // Flush pending saves on page unload and component unmount
  useEffect(() => {
    const handleBeforeUnload = () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current)
        saveTimeoutRef.current = null
      }
      if (activeDocument) {
        saveDocument(activeDocument)
      }
    }

    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload)
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current)
        saveTimeoutRef.current = null
      }
      if (activeDocument) {
        saveDocument(activeDocument)
      }
    }
  }, [activeDocument, saveDocument])


  const handleCreateDocument = async () => {
    if (!newDocTitle.trim() || isCreating) return

    try {
      setIsCreating(true)
      setError(null)
      const newDoc = await api.createDocument(goalId, userId, newDocTitle.trim(), 'notes')
      setDocuments(prev => [newDoc, ...prev])
      setActiveDocument(newDoc)
      setNewDocTitle('')
      setIsCreating(false)
    } catch (err: any) {
      setError(err.message || 'Failed to create document')
      setIsCreating(false)
    }
  }

  const handleSelectDocument = async (docId: number) => {
    try {
      const doc = await api.getDocument(docId)
      setActiveDocument(doc)
      lastKnownVersionRef.current = doc.version
    } catch (err: any) {
      setError(err.message || 'Failed to load document')
    }
  }

  const handleManualSave = async () => {
    if (!activeDocument) return

    try {
      setIsSaving(true)
      setError(null)
      await api.updateDocument(activeDocument.id, { plain_text: activeDocument.plain_text })
    } catch (err: any) {
      setError(err.message || 'Failed to save document')
    } finally {
      setIsSaving(false)
    }
  }

  // Cleanup timeout on unmount (moved to beforeunload effect)

  return (
    <div className="panel-tab draft-tab">
      <div className="panel-tab-header">
        <h3>Documents</h3>
        {activeDocument && (
          <div className="draft-header-actions">
            {isSaving && <span className="saving-indicator">Saving...</span>}
            {isGeneratingSuggestions && <span className="saving-indicator">Analyzing...</span>}
            <button 
              onClick={requestSuggestions} 
              className="suggest-btn" 
              disabled={isGeneratingSuggestions || !activeDocument || !(activeDocument.plain_text || '').trim()}
            >
              Get AI Feedback
            </button>
            <button onClick={handleManualSave} className="save-btn" disabled={isSaving}>
              Save
            </button>
          </div>
        )}
      </div>

      {error && (
        <div className="panel-error" style={{ cursor: 'pointer' }} onClick={() => setError(null)}>
          {error}
        </div>
      )}

      <div className="draft-tab-content">
        {/* Document List Sidebar */}
        <div className="draft-documents-sidebar">
          <div className="draft-create-form">
            <input
              type="text"
              className="draft-title-input"
              value={newDocTitle}
              onChange={(e) => setNewDocTitle(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleCreateDocument()}
              placeholder="New document title..."
              disabled={isCreating}
            />
            <button
              className="draft-create-btn"
              onClick={handleCreateDocument}
              disabled={!newDocTitle.trim() || isCreating}
            >
              {isCreating ? '...' : '+'}
            </button>
          </div>

          {isLoading ? (
            <div className="panel-loading">Loading documents...</div>
          ) : documents.length === 0 ? (
            <div className="panel-empty-small">
              <p>No documents yet</p>
            </div>
          ) : (
            <div className="draft-documents-list">
              {documents.map((doc) => (
                <button
                  key={doc.id}
                  className={`draft-document-item ${activeDocument?.id === doc.id ? 'active' : ''}`}
                  onClick={() => handleSelectDocument(doc.id)}
                >
                  <span className="draft-document-title">{doc.title}</span>
                  <span className="draft-document-type">{doc.document_type}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Document Editor */}
        <div className="draft-editor">
          {activeDocument ? (
            <>
              <div className="draft-editor-header">
                <input
                  type="text"
                  className="draft-editor-title"
                  value={activeDocument.title}
                  onChange={(e) => {
                    const newTitle = e.target.value
                    setActiveDocument(prev => prev ? { ...prev, title: newTitle } : null)
                  }}
                  onBlur={async () => {
                    // Save title immediately on blur
                    if (activeDocument) {
                      try {
                        await api.updateDocument(activeDocument.id, { title: activeDocument.title })
                      } catch (err) {
                        setError('Failed to save title')
                      }
                    }
                  }}
                  placeholder="Document title..."
                />
                <span className="draft-editor-meta">
                  v{activeDocument.version} • {activeDocument.document_type}
                </span>
              </div>
              <RichTextEditor
                content={activeDocument.plain_text || ''}
                onChange={(plainText, json) => handleContentChange(plainText, json)}
                onBlur={handleBlur}
                placeholder="Start writing... AI will analyze your writing and provide suggestions."
              />
              
              {/* AI Suggestions Panel */}
              {suggestions.length > 0 && (
                <div className="document-suggestions">
                  <div className="suggestions-header">
                    <h4>AI Suggestions</h4>
                    <button 
                      className="suggestions-close-btn"
                      onClick={() => setSuggestions([])}
                      title="Close suggestions"
                    >
                      ×
                    </button>
                  </div>
                  <div className="suggestions-list">
                    {suggestions.map((suggestion, idx) => {
                      const suggestionId = `${suggestion.suggestion_type}-${suggestion.text.substring(0, 50)}-${idx}`
                      const isExpanded = expandedSuggestionId === suggestionId
                      const isDisabled = isExpandingSuggestion || isExpanded
                      
                      return (
                      <div 
                        key={idx} 
                        className={`suggestion-item suggestion-${suggestion.suggestion_type} ${isDisabled ? 'disabled' : 'clickable'}`}
                        onClick={() => !isDisabled && handleSuggestionClick(suggestion, idx)}
                        title={isExpanded ? "Already sent to chat" : isExpandingSuggestion ? "Expanding..." : "Click to expand in chat"}
                      >
                        <div className="suggestion-header">
                          <span className="suggestion-type-badge">{suggestion.suggestion_type}</span>
                          {suggestion.location && (
                            <span className="suggestion-location">{suggestion.location}</span>
                          )}
                          <span className="suggestion-click-hint">Click to expand →</span>
                        </div>
                        <p className="suggestion-text">{suggestion.text}</p>
                        {isExpanded && (
                          <div className="suggestion-sent-indicator">✓ Sent to chat</div>
                        )}
                        {isExpandingSuggestion && !isExpanded && (
                          <div className="suggestion-expanding-indicator">Expanding...</div>
                        )}
                      </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="panel-empty">
              <p>No document selected</p>
              <p className="panel-empty-hint">Create a new document or select one from the list.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

