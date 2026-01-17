const API_BASE_URL = 'http://localhost:8000'

export interface ModelConfig {
  interviewer?: string
  ranker?: string
}

export interface SessionCreateResponse {
  session_id: string
  opening_message: string
  audio_url?: string
  conversation_history: Array<{ role: string; content: string }>
  is_resumed: boolean
  profile_summary?: string
}

export interface LearningStartResponse {
  opening_message: string
  audio_url?: string
  state: string
}

export interface LoginResponse {
  user_id: string
  username: string
  is_new_user: boolean
  onboarding_info?: string
}

export interface GoalData {
  id: number
  goal_text: string
  created_at: string | null
  status: string
  has_teaching_candidate: boolean
}

export interface ExplorationSession {
  session_id: string
  conversation_history: Array<{ role: string; content: string }>
  schema_state: any
  turns_elapsed: number
}

export interface UserData {
  user_id: string
  username: string
  onboarding_info: string | null
  goals: GoalData[]
  exploration_session: ExplorationSession | null
}

export const api = {
  async startDiscoverySession(
    modelConfig?: ModelConfig, 
    goal?: string,
    userId?: string,
    goalId?: number
  ): Promise<SessionCreateResponse> {
    const response = await fetch(`${API_BASE_URL}/api/discovery/start`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        models: modelConfig || {},
        goal: goal || undefined,
        user_id: userId || undefined,
        goal_id: goalId || undefined
      }),
    })

    if (!response.ok) {
      throw new Error('Failed to start discovery session')
    }

    return response.json()
  },

  async startLearningSession(sessionId: string): Promise<LearningStartResponse> {
    const response = await fetch(`${API_BASE_URL}/api/learning/start`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ session_id: sessionId }),
    })

    if (!response.ok) {
      throw new Error('Failed to start learning session')
    }

    return response.json()
  },

  async getDiscoverySchema(sessionId: string): Promise<any> {
    const response = await fetch(`${API_BASE_URL}/api/discovery/${sessionId}/schema`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    })

    if (!response.ok) {
      throw new Error('Failed to get discovery schema')
    }

    return response.json()
  },

  // User authentication and data
  async login(username: string): Promise<LoginResponse> {
    const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ username }),
    })

    if (!response.ok) {
      throw new Error('Login failed')
    }

    return response.json()
  },

  async getUserData(userId: string): Promise<UserData> {
    const response = await fetch(`${API_BASE_URL}/api/user/${userId}/data`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    })

    if (!response.ok) {
      throw new Error('Failed to get user data')
    }

    return response.json()
  },

  async createGoal(userId: string, goalText: string): Promise<{ id: number; goal_text: string }> {
    const response = await fetch(`${API_BASE_URL}/api/user/goals`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ user_id: userId, goal_text: goalText }),
    })

    if (!response.ok) {
      throw new Error('Failed to create goal')
    }

    return response.json()
  },

  async updateOnboarding(userId: string, onboardingInfo: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/api/user/${userId}/onboarding?onboarding_info=${encodeURIComponent(onboardingInfo)}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
    })

    if (!response.ok) {
      throw new Error('Failed to update onboarding')
    }
  },

  async saveProfileSummary(sessionId: string, summary: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/api/profile/summary/save`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ session_id: sessionId, summary }),
    })

    if (!response.ok) {
      throw new Error('Failed to save profile summary')
    }
  },

  // Feed content
  async getFeed(params: {
    user_id: string
    context_type: 'exploration' | 'goal' | 'teaching_candidate'
    goal_id?: number
    goal_text?: string
    teaching_candidate_id?: string
    teaching_topic?: string
    user_background?: string
    goals_summary?: string
  }): Promise<{ items: FeedItem[]; generated: boolean }> {
    const response = await fetch(`${API_BASE_URL}/api/feed`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(params),
    })

    if (!response.ok) {
      throw new Error('Failed to get feed')
    }

    return response.json()
  },
}

export interface FeedItem {
  id: number
  title: string
  content: string
  source_citation?: string
  source_url?: string
  relevance_note?: string
}
