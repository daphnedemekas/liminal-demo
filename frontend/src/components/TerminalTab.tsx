import { useState, useEffect, useRef } from 'react'
import { api, TerminalSession } from '../services/api'
import { getApiBaseUrl } from '../config'
import { stripAnsiEscapeSequences } from '../utils/textUtils'

interface TerminalTabProps {
  goalId: number
  userId: string
}

interface TerminalSuggestion {
  activity: string
  suggestion: string
  timestamp: number
}

export default function TerminalTab({ goalId, userId }: TerminalTabProps) {
  const [session, setSession] = useState<TerminalSession | null>(null)
  const [isConnecting, setIsConnecting] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const [output, setOutput] = useState<string>('')
  const [commandHistory, setCommandHistory] = useState<string[]>([])
  const [historyIndex, setHistoryIndex] = useState(-1)
  const [currentInput, setCurrentInput] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [suggestions, setSuggestions] = useState<TerminalSuggestion[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const outputRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const currentCommandRef = useRef<{ command: string; startOutput: string; isClaudeCode: boolean; lastActivityTime: number; inInteractiveMode: boolean } | null>(null)
  const claudeCodeTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  const startTerminal = async () => {
    if (session || isConnecting) return

    try {
      setIsConnecting(true)
      setError(null)
      const newSession = await api.startTerminal(goalId, userId, '~')
      setSession(newSession)
      connectWebSocket(newSession.session_id)
    } catch (err: any) {
      console.error('[TerminalTab] Failed to start terminal:', err)
      setError(err.message || 'Failed to start terminal')
      setIsConnecting(false)
    }
  }

  const connectWebSocket = (sessionId: string) => {
    const apiUrl = getApiBaseUrl().replace(/^http/, 'ws')
    const ws = new WebSocket(`${apiUrl}/ws/terminal/${sessionId}`)

    ws.onopen = () => {
      console.log('[TerminalTab] WebSocket connected')
      setIsConnected(true)
      setIsConnecting(false)
      setOutput(prev => prev + '\n[Terminal connected]\n')
      inputRef.current?.focus()
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        
        if (data.type === 'output') {
          // Strip ANSI escape sequences before displaying
          const cleanedOutput = stripAnsiEscapeSequences(data.data)
          setOutput(prev => {
            const newOutput = prev + cleanedOutput
            
            // Detect command completion: look for new prompt pattern (e.g., "$ ", "% ", "> ")
            // This indicates the previous command finished and a new prompt appeared
            if (currentCommandRef.current) {
              // Update last activity time for Claude Code commands
              if (currentCommandRef.current.isClaudeCode) {
                currentCommandRef.current.lastActivityTime = Date.now()
                
                // Detect if Claude Code is in interactive mode (showing prompts like "Enter to confirm")
                // Patterns that indicate interactive prompts from Claude Code
                const interactivePatterns = [
                  /Enter to confirm/i,
                  /Esc to cancel/i,
                  /Do you want to use/i,
                  /Quick safety check/i,
                  /Accessing workspace/i,
                  /Security guide/i,
                  /❯\s*\d+\./  // Menu options like "❯ 1. Yes"
                ]
                
                // Check if any interactive pattern is present in the output
                const hasInteractivePrompt = interactivePatterns.some(pattern => pattern.test(newOutput))
                
                if (hasInteractivePrompt && !currentCommandRef.current.inInteractiveMode) {
                  // Just entered interactive mode
                  currentCommandRef.current.inInteractiveMode = true
                  console.log('[TerminalTab] Claude Code entered interactive mode')
                } else if (hasInteractivePrompt) {
                  // Still in interactive mode - don't try to detect completion yet
                  return newOutput
                }
              }
              
              // Check if the new output chunk contains a prompt pattern (common prompts: $, %, >, #)
              // Look for prompt at the end of the accumulated output
              // Improved pattern to match various shell prompts more reliably
              const promptPattern = /[\r\n](?:[$%#>]|\w+@[\w-]+:[\w\/~]+\$|\w+@[\w-]+:[\w\/~]+[#\$])\s*$/
              
              // For Claude Code in interactive mode, we need to see a shell prompt AFTER the interactive session
              // This means we should have seen interactive prompts before, and now we see a shell prompt
              if (currentCommandRef.current.isClaudeCode && currentCommandRef.current.inInteractiveMode) {
                // Only mark as complete if we see a shell prompt (meaning interactive session ended)
                if (promptPattern.test(newOutput)) {
                  // Check that the prompt appears well after the interactive content
                  const promptMatches = [...newOutput.matchAll(new RegExp(promptPattern.source, 'g'))]
                  if (promptMatches.length > 0) {
                    const lastMatch = promptMatches[promptMatches.length - 1]
                    if (lastMatch.index !== undefined) {
                      const commandStartLength = currentCommandRef.current.startOutput.length
                      const promptStartIndex = lastMatch.index
                      
                      // Ensure we have substantial output (interactive session + completion)
                      if (promptStartIndex > commandStartLength + 200) {
                        // Interactive session completed, now we can process
                        currentCommandRef.current.inInteractiveMode = false
                        // Continue to process completion below
                      } else {
                        // Still in interactive mode, don't process yet
                        return newOutput
                      }
                    }
                  }
                } else {
                  // Still in interactive mode, no shell prompt yet
                  return newOutput
                }
              }
              
              if (promptPattern.test(newOutput)) {
                // Command completed - extract output between command start and prompt
                // Find the last prompt position
                const promptMatches = [...newOutput.matchAll(new RegExp(promptPattern.source, 'g'))]
                if (promptMatches.length > 0) {
                  // Get the last prompt match (most recent)
                  const lastMatch = promptMatches[promptMatches.length - 1]
                  if (lastMatch.index !== undefined) {
                    // Extract output: everything after the command start up to (but not including) the new prompt
                    const commandStartLength = currentCommandRef.current.startOutput.length
                    const promptStartIndex = lastMatch.index
                    
                    // For Claude Code, ensure we have substantial output (it's interactive)
                    const minOutputLength = currentCommandRef.current.isClaudeCode ? 100 : 0
                    
                    // Only process if we have a new prompt (not the one we started with)
                    // and for Claude Code, ensure we have enough output
                    if (promptStartIndex > commandStartLength + minOutputLength) {
                      const commandOutput = newOutput.substring(commandStartLength, promptStartIndex).trim()
                      
                      // Send command_complete message (even if output is empty, the command was executed)
                      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                        try {
                          wsRef.current.send(JSON.stringify({
                            type: 'command_complete',
                            command: currentCommandRef.current.command,
                            output: commandOutput,
                            exit_code: 0 // We can't reliably detect exit codes from output alone
                          }))
                          console.log('[TerminalTab] Sent command_complete:', currentCommandRef.current.command, currentCommandRef.current.isClaudeCode ? '(Claude Code)' : '')
                        } catch (err) {
                          console.error('[TerminalTab] Failed to send command_complete:', err)
                        }
                      }
                      
                      // Clear timeout if set
                      if (claudeCodeTimeoutRef.current) {
                        clearTimeout(claudeCodeTimeoutRef.current)
                        claudeCodeTimeoutRef.current = null
                      }
                      
                      // Clear current command tracking
                      currentCommandRef.current = null
                    }
                  }
                }
              } else if (currentCommandRef.current.isClaudeCode) {
                // For Claude Code, if no prompt appears after a delay, force completion
                // This handles cases where Claude Code doesn't return to prompt immediately
                const timeSinceLastActivity = Date.now() - currentCommandRef.current.lastActivityTime
                const timeSinceStart = Date.now() - (currentCommandRef.current.lastActivityTime - 1000) // Approximate start time
                
                // If we've had output recently but no prompt for 5+ seconds, and it's been 10+ seconds total
                if (timeSinceLastActivity > 5000 && timeSinceStart > 10000 && newOutput.length > currentCommandRef.current.startOutput.length + 200) {
                  // Force completion for Claude Code
                  const commandStartLength = currentCommandRef.current.startOutput.length
                  const commandOutput = newOutput.substring(commandStartLength).trim()
                  
                  if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                    try {
                      wsRef.current.send(JSON.stringify({
                        type: 'command_complete',
                        command: currentCommandRef.current.command,
                        output: commandOutput,
                        exit_code: 0
                      }))
                      console.log('[TerminalTab] Sent command_complete (Claude Code, timeout):', currentCommandRef.current.command)
                    } catch (err) {
                      console.error('[TerminalTab] Failed to send command_complete:', err)
                    }
                  }
                  
                  if (claudeCodeTimeoutRef.current) {
                    clearTimeout(claudeCodeTimeoutRef.current)
                    claudeCodeTimeoutRef.current = null
                  }
                  
                  currentCommandRef.current = null
                }
              }
            }
            
            return newOutput
          })
          
          // Auto-scroll to bottom
          setTimeout(() => {
            outputRef.current?.scrollTo(0, outputRef.current.scrollHeight)
          }, 10)
        } else if (data.type === 'observation') {
          // AI observation - display as suggestion
          console.log('[TerminalTab] AI observation:', data)
          const suggestion: TerminalSuggestion = {
            activity: data.activity || 'terminal',
            suggestion: data.suggestion || 'AI detected terminal activity',
            timestamp: Date.now()
          }
          setSuggestions(prev => [...prev, suggestion])
        }
      } catch (err) {
        // If not JSON, treat as raw output and strip ANSI sequences
        const cleanedOutput = stripAnsiEscapeSequences(event.data)
        setOutput(prev => prev + cleanedOutput)
      }
    }

    ws.onerror = (err) => {
      console.error('[TerminalTab] WebSocket error:', err)
      setError('Connection error')
      setIsConnected(false)
    }

    ws.onclose = () => {
      console.log('[TerminalTab] WebSocket closed')
      setIsConnected(false)
      setOutput(prev => prev + '\n[Terminal disconnected]\n')
    }

    wsRef.current = ws
  }

  const sendCommand = (command: string) => {
    if (!wsRef.current || !isConnected || !command.trim()) return

    // Add to history
    setCommandHistory(prev => [...prev, command])
    setHistoryIndex(-1)

    // Track current command for completion detection
    // The shell will echo the command, so we track the output length before sending
    const isClaudeCode = command.toLowerCase().trim().startsWith('claude') || command.toLowerCase().trim().startsWith('cc ')
    setOutput(prev => {
      currentCommandRef.current = {
        command: command.trim(),
        startOutput: prev, // Track from current output position (before command echo)
        isClaudeCode: isClaudeCode,
        lastActivityTime: Date.now(),
        inInteractiveMode: false // Will be set to true when we detect interactive prompts
      }
      return prev // Don't modify output here, let the shell echo handle it
    })
    
    // For Claude Code, set a timeout to force completion detection if no prompt appears
    if (isClaudeCode && claudeCodeTimeoutRef.current) {
      clearTimeout(claudeCodeTimeoutRef.current)
    }

    // Send command
    wsRef.current.send(JSON.stringify({
      type: 'input',
      data: command + '\n'
    }))

    setCurrentInput('')
  }

  const dismissSuggestion = (timestamp: number) => {
    setSuggestions(prev => prev.filter(s => s.timestamp !== timestamp))
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      sendCommand(currentInput)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (commandHistory.length > 0) {
        const newIndex = historyIndex === -1 
          ? commandHistory.length - 1 
          : Math.max(0, historyIndex - 1)
        setHistoryIndex(newIndex)
        setCurrentInput(commandHistory[newIndex])
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (historyIndex >= 0) {
        const newIndex = historyIndex + 1
        if (newIndex >= commandHistory.length) {
          setHistoryIndex(-1)
          setCurrentInput('')
        } else {
          setHistoryIndex(newIndex)
          setCurrentInput(commandHistory[newIndex])
        }
      }
    }
  }

  // Auto-focus input when connected
  useEffect(() => {
    if (isConnected) {
      inputRef.current?.focus()
    }
  }, [isConnected])

  // Cleanup WebSocket and timeouts on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
      if (claudeCodeTimeoutRef.current) {
        clearTimeout(claudeCodeTimeoutRef.current)
      }
    }
  }, [])

  return (
    <div className="panel-tab terminal-tab">
      <div className="panel-tab-header">
        <h3>Terminal</h3>
        {!session && (
          <button
            className="terminal-start-btn"
            onClick={startTerminal}
            disabled={isConnecting}
          >
            {isConnecting ? 'Starting...' : 'Start Terminal'}
          </button>
        )}
        {session && (
          <div className="terminal-status">
            <span className={`terminal-status-dot ${isConnected ? 'connected' : 'disconnected'}`}></span>
            {isConnected ? 'Connected' : 'Disconnected'}
          </div>
        )}
      </div>

      {error && (
        <div className="panel-error">
          {error}
        </div>
      )}

      <div className="terminal-tab-content">
        {!session ? (
          <div className="panel-empty">
            <p>Terminal not started</p>
            <p className="panel-empty-hint">Click "Start Terminal" to begin an interactive terminal session.</p>
            <p className="panel-empty-hint">The AI can observe your terminal activity and provide suggestions.</p>
          </div>
        ) : (
          <>
            {/* AI Suggestions Banner */}
            {suggestions.length > 0 && (
              <div className="terminal-suggestions">
                {suggestions.map((suggestion) => (
                  <div key={suggestion.timestamp} className="terminal-suggestion-banner">
                    <div className="terminal-suggestion-content">
                      <strong>AI Observation:</strong> {suggestion.suggestion}
                      {suggestion.activity && suggestion.activity !== 'terminal' && (
                        <span className="terminal-activity-badge">{suggestion.activity}</span>
                      )}
                    </div>
                    <button
                      className="terminal-suggestion-dismiss"
                      onClick={() => dismissSuggestion(suggestion.timestamp)}
                      title="Dismiss"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div
              ref={outputRef}
              className="terminal-output"
            >
              <pre>{output || '[Terminal ready]\n'}</pre>
            </div>
            <div className="terminal-input-container">
              <span className="terminal-prompt">$</span>
              <input
                ref={inputRef}
                type="text"
                className="terminal-input"
                value={currentInput}
                onChange={(e) => setCurrentInput(e.target.value)}
                onKeyDown={handleKeyPress}
                placeholder={isConnected ? "Type a command..." : "Connecting..."}
                disabled={!isConnected}
                autoFocus
              />
            </div>
          </>
        )}
      </div>
    </div>
  )
}



