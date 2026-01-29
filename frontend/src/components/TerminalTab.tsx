import { useState, useEffect, useRef } from 'react'
import { api, TerminalSession } from '../services/api'
import { getApiBaseUrl } from '../config'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'

interface TerminalTabProps {
  goalId: number
  userId: string
}

interface TerminalSuggestion {
  activity: string
  suggestion: string
  timestamp: number
  isError?: boolean
  learningOpportunity?: string
  command?: string
}

export default function TerminalTab({ goalId, userId }: TerminalTabProps) {
  const storageKey = `terminal_session_${goalId}`
  const [session, setSession] = useState<TerminalSession | null>(() => {
    const saved = sessionStorage.getItem(storageKey)
    if (saved) {
      try { return JSON.parse(saved) } catch { /* ignore */ }
    }
    return null
  })
  const [isConnecting, setIsConnecting] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [suggestions, setSuggestions] = useState<TerminalSuggestion[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const terminalRef = useRef<HTMLDivElement>(null)
  const xtermRef = useRef<Terminal | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const currentCommandRef = useRef<{ command: string; startOutput: string; isClaudeCode: boolean; lastActivityTime: number; inInteractiveMode: boolean } | null>(null)
  const claudeCodeTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const outputBufferRef = useRef<string>('')
  const inputLineRef = useRef<string>('')  // Accumulates typed characters to build command string

  const initXterm = () => {
    if (!terminalRef.current || xtermRef.current) return

    const term = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: '"SF Mono", "Cascadia Code", "Fira Code", Menlo, Monaco, "Courier New", monospace',
      theme: {
        background: '#1e1e2e',
        foreground: '#cdd6f4',
        cursor: '#f5e0dc',
        selectionBackground: '#585b7066',
        black: '#45475a',
        red: '#f38ba8',
        green: '#a6e3a1',
        yellow: '#f9e2af',
        blue: '#89b4fa',
        magenta: '#f5c2e7',
        cyan: '#94e2d5',
        white: '#bac2de',
        brightBlack: '#585b70',
        brightRed: '#f38ba8',
        brightGreen: '#a6e3a1',
        brightYellow: '#f9e2af',
        brightBlue: '#89b4fa',
        brightMagenta: '#f5c2e7',
        brightCyan: '#94e2d5',
        brightWhite: '#a6adc8',
      },
      scrollback: 5000,
      convertEol: true,
    })

    const fitAddon = new FitAddon()
    term.loadAddon(fitAddon)
    term.loadAddon(new WebLinksAddon())

    term.open(terminalRef.current)
    fitAddon.fit()

    xtermRef.current = term
    fitAddonRef.current = fitAddon

    // Handle user input — send raw data to PTY via WebSocket
    term.onData((data) => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'input', data }))
      }

      // Track typed characters to build command string
      if (data === '\r' || data === '\n') {
        // Enter pressed — commit the accumulated input as the current command
        const command = inputLineRef.current.trim()
        if (command) {
          const isClaudeCode = /^(claude|cc|claude-code)\b/.test(command)
          currentCommandRef.current = {
            command,
            startOutput: '',
            isClaudeCode,
            lastActivityTime: Date.now(),
            inInteractiveMode: isClaudeCode,
          }
          // Reset output buffer for this new command
          outputBufferRef.current = ''
        }
        inputLineRef.current = ''
      } else if (data === '\x7f' || data === '\b') {
        // Backspace — remove last character
        inputLineRef.current = inputLineRef.current.slice(0, -1)
      } else if (data === '\x03') {
        // Ctrl+C — clear current input
        inputLineRef.current = ''
        currentCommandRef.current = null
      } else if (data.length === 1 && data >= ' ') {
        // Printable character
        inputLineRef.current += data
      } else if (data.length > 1 && !data.startsWith('\x1b')) {
        // Pasted text (multiple chars, not an escape sequence)
        inputLineRef.current += data
      }
    })

    // Handle resize
    term.onResize(({ cols, rows }) => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'resize', cols, rows }))
      }
    })

    // Resize observer for container
    const resizeObserver = new ResizeObserver(() => {
      try { fitAddon.fit() } catch {}
    })
    resizeObserver.observe(terminalRef.current)

    return () => {
      resizeObserver.disconnect()
      term.dispose()
      xtermRef.current = null
      fitAddonRef.current = null
    }
  }

  const startTerminal = async () => {
    if (session || isConnecting) return

    try {
      setIsConnecting(true)
      setError(null)
      const newSession = await api.startTerminal(goalId, userId, '~')
      setSession(newSession)
      sessionStorage.setItem(storageKey, JSON.stringify(newSession))
    } catch (err: any) {
      console.error('[TerminalTab] Failed to start terminal:', err)
      setError(err.message || 'Failed to start terminal')
      setIsConnecting(false)
    }
  }

  // Initialize xterm when session is created and container is ready
  useEffect(() => {
    if (!session || !terminalRef.current) return

    const cleanup = initXterm()

    // Connect WebSocket after xterm is ready
    connectWebSocket(session.session_id)

    return () => {
      cleanup?.()
    }
  }, [session])

  const connectWebSocket = (sessionId: string) => {
    const apiUrl = getApiBaseUrl().replace(/^http/, 'ws')
    const ws = new WebSocket(`${apiUrl}/ws/terminal/${sessionId}`)

    ws.onopen = () => {
      console.log('[TerminalTab] WebSocket connected')
      setIsConnected(true)
      setIsConnecting(false)
      xtermRef.current?.focus()

      // Send initial resize
      if (xtermRef.current) {
        ws.send(JSON.stringify({
          type: 'resize',
          cols: xtermRef.current.cols,
          rows: xtermRef.current.rows,
        }))
      }
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        if (data.type === 'output') {
          // Write raw output to xterm (it handles ANSI natively)
          xtermRef.current?.write(data.data)

          // Track output for command completion detection
          outputBufferRef.current += data.data
          detectCommandCompletion(data.data)
        } else if (data.type === 'observation') {
          console.log('[TerminalTab] AI observation:', data)
          const suggestion: TerminalSuggestion = {
            activity: data.activity || 'terminal',
            suggestion: data.suggestion || 'AI detected terminal activity',
            timestamp: Date.now(),
            isError: data.is_error || false,
            learningOpportunity: data.learning_opportunity,
            command: data.command,
          }
          setSuggestions(prev => [...prev, suggestion])
        }
      } catch {
        // Raw output
        xtermRef.current?.write(event.data)
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
      xtermRef.current?.write('\r\n[Terminal disconnected]\r\n')
      // Clear saved session so user can start fresh
      sessionStorage.removeItem(storageKey)
      setSession(null)
    }

    wsRef.current = ws
  }

  const detectCommandCompletion = (_newData: string) => {
    if (!currentCommandRef.current) return

    if (currentCommandRef.current.isClaudeCode) {
      currentCommandRef.current.lastActivityTime = Date.now()
    }

    // Strip ANSI escape codes for prompt detection
    const stripped = outputBufferRef.current.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '').replace(/\x1b\][^\x07]*\x07/g, '')

    // Check for shell prompt indicating command completed
    // Match common prompts: user@host:~/dir$ , ~/dir % , # , >
    const promptPattern = /[$%#>]\s*$/
    if (promptPattern.test(stripped.trimEnd()) && stripped.length > 10) {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        try {
          wsRef.current.send(JSON.stringify({
            type: 'command_complete',
            command: currentCommandRef.current.command,
            output: stripped.slice(-2000), // last 2000 chars, ANSI-stripped
            exit_code: 0
          }))
          console.log('[TerminalTab] Sent command_complete:', currentCommandRef.current.command)
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

  const dismissSuggestion = (timestamp: number) => {
    setSuggestions(prev => prev.filter(s => s.timestamp !== timestamp))
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      wsRef.current?.close()
      if (claudeCodeTimeoutRef.current) {
        clearTimeout(claudeCodeTimeoutRef.current)
      }
    }
  }, [])

  // Fit terminal when tab becomes visible
  useEffect(() => {
    const fitTimer = setInterval(() => {
      try { fitAddonRef.current?.fit() } catch {}
    }, 1000)
    return () => clearInterval(fitTimer)
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
                  <div key={suggestion.timestamp} className={`terminal-suggestion-banner ${suggestion.isError ? 'terminal-suggestion-error' : ''}`}>
                    <div className="terminal-suggestion-content">
                      <strong>{suggestion.isError ? 'Error Detected' : 'AI Observation'}:</strong> {suggestion.suggestion}
                      {suggestion.command && (
                        <code className="terminal-suggestion-command">{suggestion.command}</code>
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
              ref={terminalRef}
              className="terminal-xterm-container"
              style={{ width: '100%', height: '300px' }}
            />
          </>
        )}
      </div>
    </div>
  )
}
