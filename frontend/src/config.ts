/**
 * Get the API base URL for the current environment.
 *
 * Priority:
 * 1. VITE_API_URL environment variable (if set)
 * 2. window.location.origin if NOT localhost (deployed)
 * 3. http://localhost:8000 for local development
 */
export function getApiBaseUrl(): string {
  // Check environment variable first
  if (import.meta.env.VITE_API_URL) {
    console.log('[Config] Using VITE_API_URL:', import.meta.env.VITE_API_URL)
    return import.meta.env.VITE_API_URL
  }

  // If running in browser and NOT on localhost, use same origin (for Railway or any deployment)
  if (typeof window !== 'undefined') {
    const origin = window.location.origin
    const hostname = window.location.hostname

    // If not localhost, assume we're deployed and backend is at same origin
    if (!hostname.includes('localhost') && !hostname.includes('127.0.0.1')) {
      console.log('[Config] Using window.location.origin for deployed environment:', origin)
      return origin
    }
  }

  // Default to localhost for development
  console.log('[Config] Using localhost:8000 for local development')
  return 'http://localhost:8000'
}
