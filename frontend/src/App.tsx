import { useState, useCallback, useEffect } from 'react'
import DiscoveryChat from './components/DiscoveryChat'
import GoalChat from './components/GoalChat'
import TeachingChat from './components/TeachingChat'
import ModelSelector, { ModelConfig } from './components/ModelSelector'
import OnboardingScreen from './components/OnboardingScreen'
import LoginScreen from './components/LoginScreen'
import Sidebar, { GoalSession, TeachingCandidate } from './components/Sidebar'
import { api, GoalData } from './services/api'

type Phase = 'login' | 'config' | 'onboarding' | 'discovery'

interface User {
  id: string
  username: string
}

function App() {
  const [phase, setPhase] = useState<Phase>('login')
  const [onboardingInfo, setOnboardingInfo] = useState<string>('')
  const [modelConfig, setModelConfig] = useState<ModelConfig>({
    interviewer: 'openai:gpt-4o',
    ranker: 'openai:gpt-4o',
  })

  // User state
  const [user, setUser] = useState<User | null>(null)
  const [isLoadingUserData, setIsLoadingUserData] = useState(false)

  // Sidebar state
  const [goalSessions, setGoalSessions] = useState<GoalSession[]>([])
  const [activeGoalSessionId, setActiveGoalSessionId] = useState<string | null>(null)
  const [activeTeachingId, setActiveTeachingId] = useState<number | null>(null)

  // Derived: what are we viewing?
  const isViewingExploration = activeGoalSessionId === null
  const isViewingTeaching = activeTeachingId !== null

  // Load user data when logged in
  const loadUserData = useCallback(async (userId: string) => {
    setIsLoadingUserData(true)
    try {
      const userData = await api.getUserData(userId)
      
      // Convert goals to GoalSession format
      const loadedGoals: GoalSession[] = userData.goals.map((g: GoalData) => ({
        id: g.id.toString(),
        goalId: g.id,
        goal: g.goal_text,
        createdAt: g.created_at ? new Date(g.created_at) : new Date(),
        isActive: g.status === 'active',
        // Convert single teaching_candidate to array format
        teachingCandidates: g.teaching_candidate ? [g.teaching_candidate] : [],
      }))
      
      setGoalSessions(loadedGoals)
      
      if (userData.onboarding_info) {
        setOnboardingInfo(userData.onboarding_info)
      }
      
      console.log('[App] Loaded user data:', {
        goals: loadedGoals.length,
        hasOnboarding: !!userData.onboarding_info
      })
    } catch (err) {
      console.error('[App] Failed to load user data:', err)
    } finally {
      setIsLoadingUserData(false)
    }
  }, [])

  // Handle login
  const handleLogin = useCallback(async (userId: string, username: string, isNewUser: boolean, savedOnboardingInfo?: string) => {
    setUser({ id: userId, username })
    
    if (isNewUser) {
      setPhase('config')
    } else {
      await loadUserData(userId)
      if (savedOnboardingInfo) {
        setOnboardingInfo(savedOnboardingInfo)
        setPhase('discovery')
      } else {
        setPhase('config')
      }
    }
  }, [loadUserData])

  const handleModelSelect = (config: ModelConfig) => {
    setModelConfig(config)
    setPhase('onboarding')
  }

  const handleOnboardingComplete = async (info: string, goal?: string) => {
    setOnboardingInfo(info)

    // Persist onboarding info
    if (user) {
      try {
        await api.updateOnboarding(user.id, info)
      } catch (err) {
        console.error('[App] Failed to save onboarding:', err)
      }
    }

    // If the user provided an explicit goal up-front, immediately create a goal panel
    // and route them into the goal-specific chat. Exploration remains available in the sidebar.
    if (goal && goal.trim() && user) {
      try {
        await handleGoalAccepted(goal.trim(), 'onboarding')
        // Ensure we are viewing the new goal session (not exploration)
        setActiveTeachingId(null)
      } catch (err) {
        console.error('[App] Failed to create initial goal panel from onboarding goal:', err)
        // If this fails, fall back to exploration.
        setActiveGoalSessionId(null)
        setActiveTeachingId(null)
      }
    } else {
      // Default: start in exploration
      setActiveGoalSessionId(null)
      setActiveTeachingId(null)
    }

    setPhase('discovery')
  }

  // Handle when a goal is accepted in discovery chat
  const handleGoalAccepted = useCallback(async (goal: string, discoverySessionId: string) => {
    console.log('[App] Goal accepted:', goal)
    
    let goalId = 0
    let displayId = crypto.randomUUID()
    if (user) {
      try {
        const savedGoal = await api.createGoal(user.id, goal)
        goalId = savedGoal.id
        displayId = savedGoal.id.toString()
        console.log('[App] Goal saved to database:', savedGoal)
      } catch (err) {
        console.error('[App] Failed to save goal:', err)
      }
    }
    
    const newSession: GoalSession = {
      id: displayId,
      goalId: goalId,
      goal: goal,
      createdAt: new Date(),
      isActive: true,
      teachingCandidates: [],  // Empty initially
    }
    
    setGoalSessions(prev => [...prev, newSession])
    setActiveGoalSessionId(newSession.id)
    setActiveTeachingId(null)  // Clear any teaching selection
  }, [user])

  // Handle sidebar navigation - select a goal
  const handleSelectSession = (sessionId: string | null) => {
    if (sessionId === null) {
      // Go to exploration
      setActiveGoalSessionId(null)
      setActiveTeachingId(null)
    } else {
      // Select goal (not a specific teaching candidate)
      setActiveGoalSessionId(sessionId)
      setActiveTeachingId(null)
    }
  }

  // Handle selecting a teaching candidate
  const handleSelectTeaching = (goalSessionId: string, teachingId: number) => {
    setActiveGoalSessionId(goalSessionId)
    setActiveTeachingId(teachingId)
  }

  const handleNewExploration = () => {
    setActiveGoalSessionId(null)
    setActiveTeachingId(null)
  }

  // Handle when teaching candidate is accepted - ADD to goal's teaching list
  const handleTeachingCandidateAccepted = useCallback((candidate: TeachingCandidate, goalSessionId: string) => {
    console.log('[App] Teaching candidate accepted for goal:', goalSessionId, candidate)
    
    // Add the teaching candidate to the goal session
    setGoalSessions(prev => prev.map(session => 
      session.id === goalSessionId 
        ? { 
            ...session, 
            teachingCandidates: [...session.teachingCandidates, candidate]
          }
        : session
    ))
    
    // Automatically switch to the new teaching candidate view
    setActiveTeachingId(candidate.id)
  }, [])

  // Handle logout
  const handleLogout = () => {
    setUser(null)
    setGoalSessions([])
    setOnboardingInfo('')
    setPhase('login')
    setActiveGoalSessionId(null)
    setActiveTeachingId(null)
  }

  // Get the active goal session data
  const activeGoalSession = goalSessions.find(s => s.id === activeGoalSessionId)
  
  // Get the active teaching candidate (if any)
  const activeTeachingCandidate = activeGoalSession?.teachingCandidates.find(
    tc => tc.id === activeTeachingId
  )

  const showSidebar = phase === 'discovery'

  return (
    <div className="app-container">
      {phase === 'login' && (
        <LoginScreen onLogin={handleLogin} />
      )}

      {phase === 'config' && (
        <div className="config-screen">
          <div className="config-header">
            {user && (
              <div className="user-info">
                <span className="user-greeting">Welcome, {user.username}!</span>
                <button className="logout-btn" onClick={handleLogout}>Logout</button>
              </div>
            )}
          </div>
          <h1>Liminal Discovery</h1>
          <p>Choose your AI models to begin</p>
          <ModelSelector
            onModelSelect={handleModelSelect}
            initialConfig={modelConfig}
          />
        </div>
      )}

      {phase === 'onboarding' && (
        <OnboardingScreen onComplete={handleOnboardingComplete} />
      )}

      {showSidebar && (
        <div className="app-with-sidebar">
          <Sidebar
            goalSessions={goalSessions}
            activeSessionId={activeGoalSessionId}
            activeTeachingId={activeTeachingId}
            onSelectSession={handleSelectSession}
            onSelectTeaching={handleSelectTeaching}
            onNewExploration={handleNewExploration}
            isExplorationActive={isViewingExploration}
            username={user?.username}
            onLogout={handleLogout}
          />
          
          <div className="main-content">
            {isLoadingUserData && (
              <div className="loading-overlay">
                <div className="loading-spinner"></div>
                <p>Loading your data...</p>
              </div>
            )}

            {/* Exploration Panel */}
            {!isLoadingUserData && isViewingExploration && (
              <div style={{ width: '100%', height: '100%' }}>
                <DiscoveryChat
                  key={user?.id || 'anonymous-exploration'}
                  modelConfig={modelConfig}
                  onboardingInfo={onboardingInfo}
                  userId={user?.id}
                  onTopicFound={() => {}}  // No longer used
                  onGoalAccepted={handleGoalAccepted}
                />
              </div>
            )}

            {/* Goal Panel (when viewing a goal, not a teaching candidate) */}
            {activeGoalSession && user && !isLoadingUserData && !isViewingTeaching && (
              <div style={{
                display: !isViewingExploration ? 'flex' : 'none',
                width: '100%',
                height: '100%'
              }}>
                <GoalChat
                  key={activeGoalSession.id}
                  goalId={activeGoalSession.goalId}
                  goal={activeGoalSession.goal}
                  userId={user.id}
                  modelConfig={modelConfig}
                  onboardingInfo={onboardingInfo}
                  onTeachingCandidateAccepted={(candidate) =>
                    handleTeachingCandidateAccepted(candidate, activeGoalSession.id)
                  }
                />
              </div>
            )}

            {/* Teaching Panel (when viewing a specific teaching candidate) */}
            {activeGoalSession && activeTeachingCandidate && user && !isLoadingUserData && (
              <div style={{
                display: isViewingTeaching ? 'flex' : 'none',
                width: '100%',
                height: '100%'
              }}>
                <TeachingChat
                  key={activeTeachingCandidate.id}
                  candidate={activeTeachingCandidate}
                  goalId={activeGoalSession.goalId}
                  goalText={activeGoalSession.goal}
                  userId={user.id}
                  onboardingInfo={onboardingInfo}
                />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default App
