const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

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
  teaching_candidate?: {
    id: number
    topic: string
    focus_question: string
    identified_gap: string
  } | null
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

  // Teaching session management
  async startTeachingSession(params: {
    user_id: string
    goal_id: number
    goal_text: string
    teaching_candidate_id: number
    topic: string
    identified_gap: string
    focus_question: string
    goal_conversation_history?: Array<{ role: string; content: string }>
    user_background?: string
    current_model_summary?: string
    stakes_summary?: string
    llm_config?: { interviewer?: string; ranker?: string }
  }): Promise<TeachingStartResponse> {
    const response = await fetch(`${API_BASE_URL}/api/teaching/start`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(params),
    })

    if (!response.ok) {
      throw new Error('Failed to start teaching session')
    }

    return response.json()
  },

  async getTeachingState(sessionId: string): Promise<TeachingSchema> {
    const response = await fetch(`${API_BASE_URL}/api/teaching/${sessionId}/state`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    })

    if (!response.ok) {
      throw new Error('Failed to get teaching state')
    }

    return response.json()
  },

  // Learner trajectory dashboard
  async getTrajectory(userId: string): Promise<LearnerTrajectoryDashboard> {
    const response = await fetch(`${API_BASE_URL}/api/trajectory/${userId}`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    })

    if (!response.ok) {
      throw new Error('Failed to get trajectory')
    }

    return response.json()
  },

  async refreshTrajectory(userId: string): Promise<LearnerTrajectoryDashboard> {
    const response = await fetch(`${API_BASE_URL}/api/trajectory/${userId}/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })

    if (!response.ok) {
      throw new Error('Failed to refresh trajectory')
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

export interface TeachingStartResponse {
  session_id: string
  opening_message: string
  conversation_history: Array<{ role: string; content: string }>
  is_resumed: boolean
  curriculum_plan?: CurriculumPlan
}

export interface CurriculumPlan {
  topic: string
  goal_text: string
  total_steps: number
  steps: CurriculumStep[]
  current_step_id: number | null
  completed_step_ids: number[]
}

export interface CurriculumStep {
  id: number
  objective: string
  explanation_approach: string
  quick_check: string
  marker_targets: string[]
  prerequisites: number[]
  status: string
  turns_spent: number
  notes: string
}

export interface UnderstandingMarker {
  id: string
  name: string
  description: string
  level: 'not_yet' | 'developing' | 'strong'
  evidence: string[]
  notes: string
  last_assessed_turn: number
}

export interface TeachingSchema {
  session_id: string
  user_id: string
  goal_id: number
  teaching_candidate_id: number
  teaching_candidate: {
    id: number
    topic: string
    focus_question: string
    identified_gap: string
  }
  curriculum_plan: CurriculumPlan
  turns_elapsed: number
  current_step_index: number
  understanding_markers: UnderstandingMarker[]
  narrative_summary: string
  next_best_move: string
  open_questions: string[]
  prerequisite_gaps: string[]
  phase_complete: boolean
}

export interface TrajectoryHighlight {
  id?: string
  timestamp?: string
  kind: string
  summary: string
  confidence: number
  evidence_quote?: string | null
  source_session_id?: string | null
  goal_id?: number | null
}

export interface TrajectoryGoal {
  goal_id: number
  goal_text: string
  status: string
  momentum: string
  last_activity_at?: string | null
  learning_summary?: string
  next_suggested_move?: string
}

export interface LearnerTrajectoryDashboard {
  version: number
  user_id: string
  updated_at?: string | null
  insights?: string  // Cross-cutting observations about patterns connecting interests
  highlights: TrajectoryHighlight[]
  goals: TrajectoryGoal[]
  engagement: any
  learner_model: any
}
