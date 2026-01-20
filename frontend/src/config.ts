/**
 * Get the API base URL for the current environment.
 *
 * Priority:
 * 1. VITE_API_URL environment variable (if set)
 * 2. window.location.origin if deployed on Railway
 * 3. http://localhost:8000 for local development
 */
export function getApiBaseUrl(): string {
  // Check environment variable first
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL
  }

  // If running in browser and on Railway, use same origin
  if (typeof window !== 'undefined') {
    const origin = window.location.origin
    if (origin.includes('railway.app') || origin.includes('up.railway.app')) {
      return origin
    }
  }

  // Default to localhost for development
  return 'http://localhost:8000'
}
