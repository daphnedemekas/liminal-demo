import { useState, useCallback, useEffect } from 'react'
import DiscoveryChat from './components/DiscoveryChat'
import GoalChat from './components/GoalChat'
import TeachingChat from './components/TeachingChat'
import { ModelConfig } from './components/ModelSelector'
import LoginScreen from './components/LoginScreen'
import TrajectoryPanel from './components/TrajectoryPanel'
import Sidebar, { GoalSession, TeachingCandidate } from './components/Sidebar'
import { api, GoalData } from './services/api'

type Phase = 'login' | 'discovery'
type MainView = 'trajectory' | 'exploration' | 'goal' | 'teaching'

interface User {
  id: string
  username: string
}

function App() {
  const [phase, setPhase] = useState<Phase>('login')
  const [onboardingInfo, setOnboardingInfo] = useState<string>('')
  const [currentModel, setCurrentModel] = useState<string>('openai:gpt-4o')
  
  // Derive modelConfig from single model selection (both interviewer and ranker use same model)
  const modelConfig: ModelConfig = {
    interviewer: currentModel,
    ranker: currentModel,
  }
  
  const handleModelChange = (model: string) => {
    setCurrentModel(model)
  }

  // User state
  const [user, setUser] = useState<User | null>(null)
  const [isLoadingUserData, setIsLoadingUserData] = useState(false)

  // Sidebar state
  const [goalSessions, setGoalSessions] = useState<GoalSession[]>([])
  const [activeGoalSessionId, setActiveGoalSessionId] = useState<string | null>(null)
  const [activeTeachingId, setActiveTeachingId] = useState<number | null>(null)
  const [activeMainView, setActiveMainView] = useState<MainView>('exploration')

  // Derived: what are we viewing?
  const isViewingTrajectory = activeMainView === 'trajectory'
  const isViewingExploration = activeMainView === 'exploration'
  const isViewingTeaching = activeMainView === 'teaching'

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
        teachingCandidates: Array.isArray(g.teaching_candidate) ? g.teaching_candidate : (g.teaching_candidate ? [g.teaching_candidate] : []),
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

  // Handle login - go directly to discovery (skip model selection)
  const handleLogin = useCallback(async (userId: string, username: string, isNewUser: boolean, savedOnboardingInfo?: string) => {
    setUser({ id: userId, username })
    
    if (!isNewUser) {
      await loadUserData(userId)
      if (savedOnboardingInfo) {
        setOnboardingInfo(savedOnboardingInfo)
      }
    }
    
    // Always go directly to discovery
    setActiveGoalSessionId(null)
    setActiveTeachingId(null)
    setActiveMainView('exploration')
    setPhase('discovery')
  }, [loadUserData])


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
    setActiveMainView('goal')
  }, [user])

  // Handle sidebar navigation - select a goal
  const handleSelectSession = (sessionId: string | null) => {
    if (sessionId === null) {
      // Go to exploration
      setActiveGoalSessionId(null)
      setActiveTeachingId(null)
      setActiveMainView('exploration')
    } else {
      // Select goal (not a specific teaching candidate)
      setActiveGoalSessionId(sessionId)
      setActiveTeachingId(null)
      setActiveMainView('goal')
    }
  }

  // Handle selecting a teaching candidate
  const handleSelectTeaching = (goalSessionId: string, teachingId: number) => {
    setActiveGoalSessionId(goalSessionId)
    setActiveTeachingId(teachingId)
    setActiveMainView('teaching')
  }

  const handleNewExploration = () => {
    setActiveGoalSessionId(null)
    setActiveTeachingId(null)
    setActiveMainView('exploration')
  }

  const handleSelectTrajectory = () => {
    setActiveMainView('trajectory')
  }

  // Handle when teaching candidate is accepted - ADD to goal's teaching list (with deduplication)
  const handleTeachingCandidateAccepted = useCallback((candidate: TeachingCandidate, goalSessionId: string) => {
    console.log('[App] Teaching candidate accepted for goal:', goalSessionId, candidate)

    // Add the teaching candidate to the goal session (only if not already present)
    setGoalSessions(prev => prev.map(session =>
      session.id === goalSessionId
        ? {
            ...session,
            // Deduplicate by ID - don't add if candidate already exists
            teachingCandidates: session.teachingCandidates.some(tc => tc.id === candidate.id)
              ? session.teachingCandidates
              : [...session.teachingCandidates, candidate]
          }
        : session
    ))

    // Automatically switch to the new teaching candidate view
    setActiveTeachingId(candidate.id)
  }, [])

  // Handle when curriculum is accepted - ADD all tasks to goal's teaching list
  const handleCurriculumAccepted = useCallback((tasks: TeachingCandidate[]) => {
    if (!activeGoalSessionId) return

    console.log('[App] Curriculum accepted with tasks:', tasks.length)

    // Add all tasks to the active goal session
    setGoalSessions(prev => prev.map(session =>
      session.id === activeGoalSessionId
        ? {
            ...session,
            teachingCandidates: tasks  // Replace with new curriculum
          }
        : session
    ))

    // Automatically select the first available task
    const firstAvailable = tasks.find(t => t.status === 'available')
    if (firstAvailable) {
      setActiveTeachingId(firstAvailable.id)
      setActiveMainView('teaching')
    }
  }, [activeGoalSessionId])

  // Handle logout
  const handleLogout = () => {
    setUser(null)
    setGoalSessions([])
    setOnboardingInfo('')
    setPhase('login')
    setActiveGoalSessionId(null)
    setActiveTeachingId(null)
    setActiveMainView('exploration')
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


      {showSidebar && (
        <div className="app-with-sidebar">
          <Sidebar
            goalSessions={goalSessions}
            activeSessionId={activeGoalSessionId}
            activeTeachingId={activeTeachingId}
            isTrajectoryActive={isViewingTrajectory}
            onSelectTrajectory={user ? handleSelectTrajectory : undefined}
            onSelectSession={handleSelectSession}
            onSelectTeaching={handleSelectTeaching}
            onNewExploration={handleNewExploration}
            isExplorationActive={isViewingExploration}
            username={user?.username}
            onLogout={handleLogout}
            currentModel={currentModel}
            onModelChange={handleModelChange}
          />
          
          <div className="main-content">
            {isLoadingUserData && (
              <div className="loading-overlay">
                <div className="loading-spinner"></div>
                <p>Loading your data...</p>
              </div>
            )}

            {/* Trajectory Panel - kept mounted, hidden when not active */}
            {!isLoadingUserData && user && (
              <div style={{ 
                display: isViewingTrajectory ? 'flex' : 'none',
                width: '100%', 
                height: '100%' 
              }}>
                <TrajectoryPanel userId={user.id} />
              </div>
            )}

            {/* Exploration Panel - kept mounted, hidden when not active */}
            {!isLoadingUserData && (
              <div style={{ 
                display: isViewingExploration ? 'flex' : 'none',
                width: '100%', 
                height: '100%' 
              }}>
                <DiscoveryChat
                  key={user?.id || 'anonymous-exploration'}
                  modelConfig={modelConfig}
                  onboardingInfo={onboardingInfo}
                  userId={user?.id}
                  onTopicFound={() => {}}  // No longer used
                  onGoalAccepted={handleGoalAccepted}
                  onBackgroundCollected={(info) => setOnboardingInfo(info)}
                />
              </div>
            )}

            {/* Goal Panels - render ALL goals, show/hide based on selection */}
            {!isLoadingUserData && user && goalSessions.map(session => (
              <div 
                key={`goal-${session.id}`}
                style={{
                  display: (activeMainView === 'goal' && activeGoalSessionId === session.id) ? 'flex' : 'none',
                  width: '100%',
                  height: '100%'
                }}
              >
                <GoalChat
                  goalId={session.goalId}
                  goal={session.goal}
                  userId={user.id}
                  modelConfig={modelConfig}
                  onboardingInfo={onboardingInfo}
                  onTeachingCandidateAccepted={(candidate) =>
                    handleTeachingCandidateAccepted(candidate, session.id)
                  }
                  onCurriculumAccepted={handleCurriculumAccepted}
                />
              </div>
            ))}

            {/* Teaching Panels - render ALL teaching candidates, show/hide based on selection */}
            {!isLoadingUserData && user && goalSessions.flatMap(session => 
              session.teachingCandidates.map(candidate => (
                <div 
                  key={`teaching-${candidate.id}`}
                  style={{
                    display: (isViewingTeaching && activeTeachingId === candidate.id) ? 'flex' : 'none',
                    width: '100%',
                    height: '100%'
                  }}
                >
                  <TeachingChat
                    candidate={candidate}
                    goalId={session.goalId}
                    goalText={session.goal}
                    userId={user.id}
                    onboardingInfo={onboardingInfo}
                    modelConfig={modelConfig}
                  />
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default App
