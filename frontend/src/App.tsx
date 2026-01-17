import { useState, useCallback, useEffect } from 'react'
import DiscoveryChat from './components/DiscoveryChat'
import GoalChat from './components/GoalChat'
import TransitionScreen from './components/TransitionScreen'
import LearningChat from './components/LearningChat'
import ModelSelector, { ModelConfig } from './components/ModelSelector'
import OnboardingScreen from './components/OnboardingScreen'
import LoginScreen from './components/LoginScreen'
import Sidebar, { GoalSession } from './components/Sidebar'
import { api, GoalData } from './services/api'

type Phase = 'login' | 'config' | 'onboarding' | 'discovery' | 'transition' | 'learning'
type View = 'exploration' | 'goal'

interface FinalTopic {
  topic: string
  user_confusion: string
  stakes: string
  learning_hook: string
  suggested_angles: string[]
  scores: Record<string, number>
}

interface User {
  id: string
  username: string
}

function App() {
  const [phase, setPhase] = useState<Phase>('login')
  const [sessionId] = useState<string>(() => crypto.randomUUID())
  const [finalTopic, setFinalTopic] = useState<FinalTopic | null>(null)
  const [onboardingInfo, setOnboardingInfo] = useState<string>('')
  const [userGoal, setUserGoal] = useState<string | undefined>(undefined)
  const [modelConfig, setModelConfig] = useState<ModelConfig>({
    interviewer: 'openai:gpt-4o',
    ranker: 'openai:gpt-4o',
  })

  // User state
  const [user, setUser] = useState<User | null>(null)
  const [isLoadingUserData, setIsLoadingUserData] = useState(false)

  // Sidebar state
  const [goalSessions, setGoalSessions] = useState<GoalSession[]>([])
  const [activeView, setActiveView] = useState<View>('exploration')
  const [activeGoalSessionId, setActiveGoalSessionId] = useState<string | null>(null)

  // Load user data when logged in
  const loadUserData = useCallback(async (userId: string) => {
    setIsLoadingUserData(true)
    try {
      const userData = await api.getUserData(userId)
      
      // Convert goals to GoalSession format
      const loadedGoals: GoalSession[] = userData.goals.map((g: GoalData) => ({
        id: g.id.toString(),
        goalId: g.id,  // Database ID for API calls
        goal: g.goal_text,
        createdAt: g.created_at ? new Date(g.created_at) : new Date(),
        isActive: g.status === 'active',
        hasTeachingCandidate: g.has_teaching_candidate,
      }))
      
      setGoalSessions(loadedGoals)
      
      // Load onboarding info if exists
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
      // New user - go to config then onboarding
      setPhase('config')
    } else {
      // Existing user - load their data and go to discovery
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
    setUserGoal(goal)
    
    // Save onboarding info to database
    if (user) {
      try {
        await api.updateOnboarding(user.id, info)
      } catch (err) {
        console.error('[App] Failed to save onboarding:', err)
      }
    }
    
    setPhase('discovery')
  }

  // Handle when a goal is accepted in discovery chat
  const handleGoalAccepted = useCallback(async (goal: string, discoverySessionId: string) => {
    console.log('[App] Goal accepted:', goal)
    
    // Save goal to database
    let goalId = 0  // Will be set from database
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
    
    // Create a new goal session
    const newSession: GoalSession = {
      id: displayId,
      goalId: goalId,
      goal: goal,
      createdAt: new Date(),
      isActive: true,
      hasTeachingCandidate: false,
    }
    
    setGoalSessions(prev => [...prev, newSession])
    
    // Switch to the new goal session
    setActiveGoalSessionId(newSession.id)
    setActiveView('goal')
  }, [user])

  // Handle sidebar navigation
  const handleSelectSession = (sessionId: string | null) => {
    if (sessionId === null) {
      // Go back to exploration
      setActiveView('exploration')
      setActiveGoalSessionId(null)
    } else {
      setActiveView('goal')
      setActiveGoalSessionId(sessionId)
    }
  }

  const handleNewExploration = () => {
    setActiveView('exploration')
    setActiveGoalSessionId(null)
  }

  // Handle when teaching candidate is accepted for a goal
  const handleTeachingCandidateAccepted = useCallback((candidate: any, goalSessionId: string) => {
    console.log('[App] Teaching candidate accepted for goal:', goalSessionId, candidate)
    
    // Update the goal session with teaching candidate info
    setGoalSessions(prev => prev.map(session => 
      session.id === goalSessionId 
        ? { ...session, hasTeachingCandidate: true, teachingCandidate: candidate }
        : session
    ))
    
    // Store the final topic and transition to learning
    setFinalTopic({
      topic: candidate.topic,
      user_confusion: candidate.identified_gap,
      stakes: '',
      learning_hook: candidate.focus_question,
      suggested_angles: [],
      scores: { readiness: candidate.readiness_score }
    })
    setPhase('transition')
  }, [])

  // Handle logout
  const handleLogout = () => {
    setUser(null)
    setGoalSessions([])
    setOnboardingInfo('')
    setPhase('login')
    setActiveView('exploration')
    setActiveGoalSessionId(null)
  }

  // Get the active goal session data
  const activeGoalSession = goalSessions.find(s => s.id === activeGoalSessionId)

  // Show sidebar only after onboarding is complete
  const showSidebar = phase === 'discovery' || phase === 'transition' || phase === 'learning'

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
            onSelectSession={handleSelectSession}
            onNewExploration={handleNewExploration}
            isExplorationActive={activeView === 'exploration'}
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

            {/* Keep exploration panel mounted to preserve state */}
            {phase === 'discovery' && !isLoadingUserData && (
              <div style={{ display: activeView === 'exploration' ? 'block' : 'none' }}>
                <DiscoveryChat
                  key={user?.id || sessionId}  // Force remount when user changes
                  sessionId={sessionId}
                  modelConfig={modelConfig}
                  onboardingInfo={onboardingInfo}
                  userGoal={userGoal}
                  userId={user?.id}
                  onTopicFound={(topic) => {
                    setFinalTopic(topic)
                    setPhase('transition')
                  }}
                  onGoalAccepted={handleGoalAccepted}
                />
              </div>
            )}

            {/* Keep goal panels mounted to preserve state */}
            {phase === 'discovery' && activeGoalSession && user && !isLoadingUserData && (
              <div style={{ display: activeView === 'goal' ? 'block' : 'none' }}>
                <GoalChat
                  key={activeGoalSession.id}  // Force remount when switching goals
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

            {phase === 'transition' && finalTopic && (
              <TransitionScreen
                topic={finalTopic}
                onStartLearning={() => setPhase('learning')}
              />
            )}

            {phase === 'learning' && finalTopic && (
              <LearningChat
                sessionId={sessionId}
              />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default App
