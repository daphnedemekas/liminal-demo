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

### Issue 4: WebSocket Reconnection Timing (Observed - Not Fixed)
**File:** `frontend/src/hooks/useWebSocket.ts`
**Severity:** Medium
**Description:** When navigating between Discovery and Goal panels, WebSocket disconnect/reconnect can be slow. The "Connecting..." state persists for several seconds.

**Potential Improvements:**
- Add connection timeout with auto-retry
- Show more informative connection state (e.g., "Retrying...")
- Consider connection pooling or keep-alive

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
});
```

### Issue 5: Profile Summary Prompt Too Sycophantic (FIXED)
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

## Future Issues to Watch For

1. **Race conditions** in concurrent WebSocket operations
2. **Memory leaks** from WebSocket connections not being cleaned up
3. **State synchronization** between frontend and backend schemas
4. **Error handling** for LLM API failures (rate limits, timeouts)
5. **Database integrity** when sessions are created/updated concurrently

---

*Last updated: 2026-01-17*

