import { useState, useCallback } from 'react'
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
  console.log('[App] Rendering App component')
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
      const loadedGoals: GoalSession[] = userData.goals.map((g: GoalData) => {
        const candidates = Array.isArray(g.teaching_candidate) ? g.teaching_candidate : (g.teaching_candidate ? [g.teaching_candidate] : [])
        // Map to TeachingCandidate format with required fields
        const teachingCandidates: TeachingCandidate[] = candidates.map((tc: any) => ({
          id: tc.id || 0,
          topic: tc.topic || '',
          focus_question: tc.focus_question || '',
          identified_gap: tc.identified_gap || '',
          readiness_score: tc.readiness_score || 0.5,
          status: (tc.status || 'locked') as TeachingCandidate['status'],
          goalConversationHistory: tc.goalConversationHistory
        }))
        
        return {
          id: g.id.toString(),
          goalId: g.id,
          goal: g.goal_text,
          createdAt: g.created_at ? new Date(g.created_at) : new Date(),
          isActive: g.status === 'active',
          teachingCandidates,
        }
      })
      
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
    console.log('[App] handleLogin called:', { userId, username, isNewUser })
    try {
      setUser({ id: userId, username })
      
      if (!isNewUser) {
        console.log('[App] Loading user data for existing user')
        await loadUserData(userId)
        if (savedOnboardingInfo) {
          setOnboardingInfo(savedOnboardingInfo)
        }
      }
      
      // Always go directly to discovery
      console.log('[App] Setting phase to discovery')
      setActiveGoalSessionId(null)
      setActiveTeachingId(null)
      setActiveMainView('exploration')
      setPhase('discovery')
      console.log('[App] Login complete')
    } catch (error) {
      console.error('[App] Error in handleLogin:', error)
      // Keep user on login screen if there's an error
    }
  }, [loadUserData])


  // Handle when a goal is accepted in discovery chat
  const handleGoalAccepted = useCallback(async (goal: string, _discoverySessionId: string) => {
    console.log('[App] Goal accepted:', goal)
    
    let goalId = 0
    let displayId: string = crypto.randomUUID()
    if (user) {
      try {
        const savedGoal = await api.createGoal(user.id, goal)
        goalId = savedGoal.id
        displayId = savedGoal.id.toString() as string
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
  const handleTeachingCandidateAccepted = useCallback((candidate: any, goalSessionId: string) => {
    console.log('[App] Teaching candidate accepted for goal:', goalSessionId, candidate)

    // Convert to Sidebar's TeachingCandidate format
    const sidebarCandidate: TeachingCandidate = {
      id: candidate.id,
      topic: candidate.topic,
      focus_question: candidate.focus_question || '',
      identified_gap: candidate.identified_gap || '',
      readiness_score: candidate.readiness_score ?? 0.5,
      status: candidate.status || 'available',
      goalConversationHistory: candidate.goalConversationHistory
    }

    // Add the teaching candidate to the goal session (only if not already present)
    setGoalSessions(prev => prev.map(session =>
      session.id === goalSessionId
        ? {
            ...session,
            // Deduplicate by ID - don't add if candidate already exists
            teachingCandidates: session.teachingCandidates.some(tc => tc.id === sidebarCandidate.id)
              ? session.teachingCandidates
              : [...session.teachingCandidates, sidebarCandidate]
          }
        : session
    ))

    // Automatically switch to the new teaching candidate view
    setActiveTeachingId(sidebarCandidate.id)
  }, [])

  // Handle when curriculum is accepted - ADD all tasks to goal's teaching list
  const handleCurriculumAccepted = useCallback((tasks: any[]) => {
    if (!activeGoalSessionId) return

    console.log('[App] Curriculum accepted with tasks:', tasks.length)

    // Convert to Sidebar's TeachingCandidate format
    const sidebarTasks: TeachingCandidate[] = tasks.map(t => ({
      id: t.id,
      topic: t.topic,
      focus_question: t.focus_question || '',
      identified_gap: t.identified_gap || '',
      readiness_score: t.readiness_score ?? 0.5,
      status: t.status || 'available',
      goalConversationHistory: t.goalConversationHistory
    }))

    // Add all tasks to the active goal session
    setGoalSessions(prev => prev.map(session =>
      session.id === activeGoalSessionId
        ? {
            ...session,
            teachingCandidates: sidebarTasks  // Replace with new curriculum
          }
        : session
    ))

    // Automatically select the first available task
    const firstAvailable = sidebarTasks.find(t => t.status === 'available')
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
  
  // Get the active teaching candidate (if any) - commented out for now
  // const activeTeachingCandidate = activeGoalSession?.teachingCandidates.find(
  //   tc => tc.id === activeTeachingId
  // )

  const showSidebar = phase === 'discovery'

  console.log('[App] Phase:', phase, 'showSidebar:', showSidebar, 'user:', user)

  return (
    <div className="app-container" style={{ minHeight: '100vh', width: '100%', backgroundColor: '#fafafa' }}>
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
