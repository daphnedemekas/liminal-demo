import { useState } from 'react'
import { getApiBaseUrl } from '../config'

interface LoginScreenProps {
  onLogin: (userId: string, username: string, isNewUser: boolean, onboardingInfo?: string) => void
}

export default function LoginScreen({ onLogin }: LoginScreenProps) {
  const [username, setUsername] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!username.trim()) {
      setError('Please enter a username')
      return
    }

    setIsLoading(true)
    setError(null)

    try {
      const apiUrl = getApiBaseUrl()
      const response = await fetch(`${apiUrl}/api/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username: username.trim() }),
      })

      if (!response.ok) {
        throw new Error('Login failed')
      }

      const data = await response.json()
      onLogin(data.user_id, data.username, data.is_new_user, data.onboarding_info)
    } catch (err) {
      setError('Failed to login. Please try again.')
      console.error('Login error:', err)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="login-screen">
      <div className="login-container">
        <div className="login-header">
          <h1 className="login-title">Liminal</h1>
          <p className="login-subtitle">Discover what you're curious about</p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-input-group">
            <label htmlFor="username" className="login-label">
              Username
            </label>
            <input
              type="text"
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter your username"
              className="login-input"
              disabled={isLoading}
              autoFocus
            />
          </div>

          {error && (
            <div className="login-error">
              {error}
            </div>
          )}

          <button
            type="submit"
            className="login-button"
            disabled={isLoading || !username.trim()}
          >
            {isLoading ? 'Signing in...' : 'Continue'}
          </button>
        </form>

        <p className="login-note">
          New users will be created automatically
        </p>
      </div>
    </div>
  )
}

