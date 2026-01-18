# Issues Found & Suggested Tests

## Issues Found During Testing

### Issue 1: Session Initialization Failure Not Handled (FIXED)
**File:** `frontend/src/components/DiscoveryChat.tsx`
**Severity:** High
**Description:** When `api.startDiscoverySession()` failed (e.g., backend not ready), the component:
1. Logged the error but showed nothing to user
2. Set `initRef.current = true` preventing retries
3. Left user stuck with disabled input and no feedback

**Fix Applied:**
- Added `sessionError` state to display error message
- Added `retryCount` state to allow retry after failure
- Reset `initRef.current = false` on error so retry works
- Added retry button UI with proper styling

**Suggested Unit Tests:**
```typescript
describe('DiscoveryChat', () => {
  it('should show error message when session initialization fails', async () => {
    // Mock api.startDiscoverySession to reject
    // Render component
    // Assert error message is displayed
    // Assert retry button is visible
  });

  it('should retry session initialization when retry button is clicked', async () => {
    // Mock api.startDiscoverySession to reject first, then resolve
    // Click retry button
    // Assert session initializes successfully on retry
  });

  it('should hide input area when session error is present', async () => {
    // Mock api.startDiscoverySession to reject
    // Assert input area is not visible
    // Assert error message is visible instead
  });
});
```

### Issue 2: Goal Chat Missing Opening Message (FIXED)
**File:** `backend/main.py`
**Severity:** High
**Description:** When opening a Goal Chat panel for the first time, no AI opening message appeared. The chat was empty and waited for user input.

**Root Cause:** 
- When a goal is created, a session record is created in DB with empty conversation history
- When GoalChat calls `start_discovery` with `goal_id`, it finds this session
- Code set `is_resumed=True` even though `conversation_history=[]`
- Opening message was only generated when `not is_resumed`

**Fix Applied:**
```python
# Changed from:
if not is_resumed:
    opening_message = session_data.discovery_session.start()

# To:
needs_opening = not is_resumed or len(conversation_history) == 0
if needs_opening:
    opening_message = session_data.discovery_session.start()
```

**Suggested Unit Tests:**
```python
def test_goal_session_first_open_has_opening_message():
    """First time opening a goal chat should have an opening message."""
    # Create a goal without prior conversation
    # Call start_discovery with goal_id
    # Assert opening_message is not empty

def test_resumed_session_with_history_no_opening():
    """Resumed session with existing history shouldn't regenerate opening."""
    # Create session with conversation history
    # Call start_discovery
    # Assert opening_message is empty (use existing history)
```

### Issue 3: TeachingChat playAudio Not Defined (FIXED)
**File:** `frontend/src/components/TeachingChat.tsx`
**Severity:** Critical
**Description:** When accepting a teaching candidate and opening TeachingChat, the page crashes with `ReferenceError: playAudio is not defined`.

**Root Cause:**
- `playAudio` was used in useEffect but not destructured from `useAudio()` hook

**Fix Applied:**
```typescript
// Changed from:
const { isAudioMode, isPlaying, toggleAudioMode } = useAudio()

// To:
const { isAudioMode, isPlaying, toggleAudioMode, playAudio } = useAudio()
```

**Suggested Unit Tests:**
```typescript
test('TeachingChat renders without crashing', () => {
  render(<TeachingChat candidate={mockCandidate} goalId={1} ... />)
  // Should not throw ReferenceError
})
```

### Issue 4: Session Initialization Fails with Corrupted DB State (FIXED)
**File:** Database state / session management
**Severity:** High
**Description:** When the database contains corrupted or inconsistent session data, new login attempts can fail with "retry connection" loop where clicking retry doesn't help.

**Root Cause:**
- Corrupted database state from previous sessions (interrupted sessions, server restarts during writes)
- The `initRef.current` guard combined with stale session records can cause initialization to fail silently

**Fix Applied:**
- Clean database and restart backend resolves the issue
- For production: add database migration/cleanup scripts, better error recovery

**Suggested Prevention:**
```python
# Add to backend startup
def cleanup_stale_sessions():
    """Remove sessions older than 24 hours or with invalid state"""
    db.execute("DELETE FROM sessions WHERE updated_at < datetime('now', '-1 day')")
```

**Suggested Unit Tests:**
```typescript
test('session initialization handles corrupted DB gracefully', async () => {
  // Mock API to return invalid session data
  // Verify error message shown and retry works
})
```

### Issue 5: Teaching Session Not Receiving Model Config (FIXED)
**File:** `backend/main.py`, `frontend/src/components/TeachingChat.tsx`, `frontend/src/App.tsx`
**Severity:** High
**Description:** Teaching session was not receiving the model_config from the frontend, causing it to fall back to default Anthropic Claude models which failed due to API credit issues.

**Root Cause:**
- `TeachingStartRequest` in backend didn't have `model_config` field
- `TeachingOrchestrator` instantiation didn't pass `model_config`
- Frontend `TeachingChat` didn't receive or send `modelConfig`

**Fix Applied:**
1. Added `model_config: Optional[dict] = None` to `TeachingStartRequest`
2. Pass `model_config=request.model_config` to `TeachingOrchestrator`
3. Added `modelConfig` prop to `TeachingChat` component
4. Pass `modelConfig` from App.tsx to TeachingChat

**Suggested Unit Tests:**
```typescript
test('TeachingChat sends model_config in API request', async () => {
  // Mock fetch and verify model_config is included
})
```

### Issue 6: WebSocket Reconnection Timing (FIXED)
**File:** `frontend/src/hooks/useWebSocket.ts`
**Severity:** Medium
**Description:** When navigating between Discovery and Goal panels, WebSocket disconnect/reconnect can be slow. The "Connecting..." state persists for several seconds.

**Fix Applied:**
- Added 5-second connection timeout
- Added auto-retry mechanism (up to 3 retries)
- Shows informative status: "Connecting...", "Retrying... (1/3)", "Connection failed. Please refresh."
- Proper cleanup of timeouts on unmount

**Suggested Unit Tests:**
```typescript
describe('useWebSocket', () => {
  it('should connect when sessionId is provided', () => {
    // Render hook with valid sessionId
    // Assert WebSocket connection is established
  });

  it('should not connect when sessionId is empty', () => {
    // Render hook with empty sessionId
    // Assert no WebSocket connection attempt
  });

  it('should reconnect when sessionId changes', () => {
    // Render hook with sessionId1
    // Update to sessionId2
    // Assert old connection closed, new connection established
  });

  it('should handle connection errors gracefully', () => {
    // Mock WebSocket to fail connection
    // Assert isConnected remains false
    // Assert no crash
  });

  it('should retry connection up to 3 times on timeout', () => {
    // Mock WebSocket to hang
    // Wait for timeout + retries
    // Assert status shows retry attempts
    // Assert max 3 retries
  });
});
```

### Issue 7: Exploration Chat Missing Recent Messages After Panel Switch (FIXED)
**File:** `frontend/src/components/DiscoveryChat.tsx`
**Severity:** Medium
**Description:** When switching from exploration → goal → teaching → exploration, the most recent messages in exploration chat are missing.

**Root Cause:**
- The `initRef.current` flag was never reset when component unmounted
- When remounting, the component would skip re-initialization because `initRef.current` was still true
- This meant conversation history was not re-fetched from backend

**Fix Applied:**
- Added cleanup effect to reset `initRef.current = false` when component unmounts
- This ensures re-initialization occurs on remount, fetching fresh conversation history

```typescript
// Reset initRef when component unmounts to allow re-initialization on remount
useEffect(() => {
  return () => {
    console.log('[DiscoveryChat] Component unmounting, resetting init flag')
    initRef.current = false
  }
}, [])
```

**Suggested Unit Tests:**
```typescript
test('Exploration chat preserves all messages after panel switch', async () => {
  // Send 3 messages in exploration
  // Switch to goal panel
  // Switch back to exploration
  // Verify all 3 messages + AI responses are visible
})

test('DiscoveryChat reinitializes on remount', async () => {
  // Mount component
  // Unmount component
  // Remount component
  // Assert api.startDiscoverySession is called again
})
```

### Issue 8: Profile Summary Prompt Too Sycophantic (FIXED)
**File:** `backend/main.py`
**Severity:** Low (UX)
**Description:** Profile summary prompt encouraged flowery language like "passionate", "unique blend", etc.

**Fix Applied:** Updated prompt to be factual and informative, explicitly prohibiting sycophantic language.

**Suggested Unit Tests:**
```python
def test_profile_summary_prompt_is_factual():
    """Ensure profile summary doesn't contain sycophantic language."""
    summary = generate_profile_summary(mock_schema_data)
    banned_words = ['passionate', 'unique', 'impressive', 'driven', 'thrives']
    for word in banned_words:
        assert word.lower() not in summary.lower()
```

---

## Suggested Integration Tests

### Test: Complete Discovery to Goal Flow
```typescript
describe('Discovery to Goal Flow', () => {
  it('should create a goal panel when goal is accepted', async () => {
    // 1. Login as test user
    // 2. Send messages in discovery chat
    // 3. Accept proposed goal
    // 4. Assert goal appears in sidebar
    // 5. Assert goal panel is created
  });

  it('should persist goal across page refresh', async () => {
    // 1. Create a goal
    // 2. Refresh page
    // 3. Login again
    // 4. Assert goal is still in sidebar
    // 5. Assert goal chat history is preserved
  });
});
```

### Test: Goal to Teaching Flow
```typescript
describe('Goal to Teaching Flow', () => {
  it('should create teaching panel when teaching candidate is accepted', async () => {
    // 1. Navigate to goal chat
    // 2. Send messages exploring the goal
    // 3. Accept proposed teaching candidate
    // 4. Assert teaching panel is created
    // 5. Assert teaching candidate is associated with goal
  });
});
```

### Test: Session Persistence
```typescript
describe('Session Persistence', () => {
  it('should restore conversation history on resume', async () => {
    // 1. Have a conversation
    // 2. Logout
    // 3. Login again
    // 4. Assert all messages are restored
    // 5. Assert schema state is preserved
  });

  it('should restore learner profile on resume', async () => {
    // 1. Build up learner profile through conversation
    // 2. Logout and login
    // 3. Assert profile attributes are preserved
  });
});
```

---

## Feature Improvements

### Improvement 1: Goal Chat Now Assesses User Level Before Proposing Teaching Candidates (IMPLEMENTED)
**Files:** 
- `prompts/ranker/teaching_discovery/generate_controller.txt`
- `prompts/ranker/teaching_discovery/update_teaching_candidates.txt`
- `prompts/ranker/teaching_discovery/update_conversational_themes_delta.txt`
- `prompts/interviewer/teaching_discovery/calibration.txt`

**Description:** Goal Chat was jumping too quickly to identifying teaching candidates without first understanding the user's current level of understanding. This could lead to mismatched teaching targets.

**Changes Applied:**
1. **Controller prompt:** Added new Step 1 "EARLY ASSESSMENT PHASE" for turns 1-2
   - New action: `assess_current_level`
   - New intent: `probe_prior_knowledge`
   - Focuses on understanding user's current knowledge before suggesting where to start

2. **Teaching candidates prompt:** Added requirement to assess level before creating candidates
   - Lists specific indicators that we understand their level
   - Instructs to return empty array if level not yet assessed
   - Added guidance on matching candidates to user's level (beginner/intermediate/advanced)

3. **Conversational themes prompt:** Prioritized "CURRENT KNOWLEDGE LEVEL" as highest priority
   - Lists specific signals to look for (self-assessment, prior experience, specific knowledge)
   - Emphasizes importance in early turns

4. **Calibration interviewer prompt:** Added assessment phase questions
   - Questions about prior experience, current understanding, past attempts
   - Pattern for acknowledging goal then assessing current relationship to topic

**Expected Behavior:**
- Turns 1-2: System asks about user's current level ("Have you explored this before?", "What parts feel solid?")
- Turn 3+: Once level is understood, system can propose appropriate teaching candidates
- Teaching candidates should match user's assessed level

**Suggested Tests:**
```python
def test_goal_chat_assesses_level_first():
    """Goal chat should ask about current level before proposing teaching candidates."""
    # Start new goal session
    # Send onboarding info
    # First AI question should probe prior knowledge/experience
    # Not immediately jump to teaching candidates

def test_teaching_candidates_not_created_without_level():
    """Teaching candidates should not be created until user level is assessed."""
    # Start goal session
    # Send vague response ("sounds interesting")
    # Check teaching_candidates should be empty
    # Send level info ("I'm a complete beginner")
    # Now teaching_candidates can be created
```

---

## Future Issues to Watch For

1. **Race conditions** in concurrent WebSocket operations
2. **Memory leaks** from WebSocket connections not being cleaned up
3. **State synchronization** between frontend and backend schemas
4. **Error handling** for LLM API failures (rate limits, timeouts)
5. **Database integrity** when sessions are created/updated concurrently

---

*Last updated: 2026-01-17*

