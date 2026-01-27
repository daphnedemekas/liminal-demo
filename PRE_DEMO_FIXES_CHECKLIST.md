# Pre-Demo Fixes Checklist

This document tracks all issues found during previous testing that must be fixed before running the demo flow.

## ✅ Already Fixed Issues

### 1. Document Error: "Document needs at least 20 characters" ✅
**Status:** FIXED
**File:** `frontend/src/components/DraftTab.tsx`
**Fix:** Updated `requestSuggestions` to check textarea value directly instead of relying on state
**Verification:** ✅ Fixed in this session

### 2. Terminal ANSI Escape Sequences Displaying ✅
**Status:** FIXED
**File:** `frontend/src/utils/textUtils.ts`, `frontend/src/components/TerminalTab.tsx`
**Fix:** Added `stripAnsiEscapeSequences()` function to filter out `[?2004h`, `[?2004l`, and other ANSI codes
**Verification:** ✅ Fixed in this session

### 3. Session Initialization Failure Handling ✅
**Status:** FIXED (from previous session)
**File:** `frontend/src/components/DiscoveryChat.tsx`
**Fix:** Added error state, retry functionality, and proper error messages

### 4. Goal Chat Missing Opening Message ✅
**Status:** FIXED (from previous session)
**File:** `backend/main.py`
**Fix:** Check for empty conversation history even when `is_resumed=True`

### 5. TeachingChat playAudio Not Defined ✅
**Status:** FIXED (from previous session)
**File:** `frontend/src/components/TeachingChat.tsx`
**Fix:** Added `playAudio` to destructured `useAudio()` hook

### 6. Teaching Session Model Config ✅
**Status:** FIXED (from previous session)
**File:** `backend/main.py`, `frontend/src/components/TeachingChat.tsx`
**Fix:** Added model_config to TeachingStartRequest and passed through components

---

## ⚠️ Issues to Fix Before Demo

### 1. Terminal AI Suggestions Not Displaying ✅
**Status:** FIXED
**Priority:** HIGH
**Files:** 
- `frontend/src/components/TerminalTab.tsx`
- `backend/main.py` (may need enhancement)

**Issue:**
- Backend sends observation messages via WebSocket
- Frontend receives them but only logs to console
- No UI to display suggestions to user

**Required Fix:**
- Add state for storing AI suggestions/observations
- Display suggestions in UI (banner, panel, or inline)
- Format suggestions nicely
- Allow user to dismiss or interact with suggestions

**Reference:** See `TERMINAL_AI_SUGGESTIONS_PLAN.md`

---

### 2. Terminal Command Completion Not Detected ✅
**Status:** FIXED
**Priority:** HIGH
**Files:**
- `frontend/src/components/TerminalTab.tsx`

**Issue:**
- Backend expects `command_complete` messages to trigger observation processing
- Frontend doesn't send these messages
- Terminal observer can't process commands without completion signals

**Required Fix:**
- Detect when commands complete (new prompt appears, command finishes)
- Send `command_complete` message with:
  - Command text
  - Output
  - Exit code
- Track command start/end in terminal output

---

### 3. Curriculum Generation Display Issue ✅
**Status:** FIXED (from previous session)
**File:** `backend/main.py`, `src/agents/orchestrator.py`, `frontend/src/components/MessageBubble.tsx`
**Fix:** Fixed raw JSON appearing in chat - now sends clean message and structured curriculum data separately

**Verification Needed:**
- [ ] Verify curriculum generation completes successfully
- [ ] Verify curriculum displays correctly (not as raw JSON)
- [ ] Verify Accept/Modify buttons appear

---

### 4. Context Usage in AI Responses ⚠️
**Status:** NEEDS VERIFICATION
**Priority:** MEDIUM
**Files:**
- `src/prompt/gather.py`
- `src/agents/orchestrator.py`

**Issue:**
- Context items can be added successfully
- Need to verify AI actually references them in responses

**Required Verification:**
- Add context item
- Ask question related to context
- Verify AI response references the context
- Check backend logs for context gathering

---

### 5. Document Auto-Suggestions ⚠️
**Status:** NEEDS VERIFICATION
**Priority:** MEDIUM
**Files:**
- `frontend/src/components/DraftTab.tsx`
- `backend/services/document_suggestion.py`

**Issue:**
- Document creation works
- Need to verify auto-suggestions appear and work correctly
- Need to verify "Get AI Feedback" works after fix

**Required Verification:**
- Type content in document
- Wait for auto-suggestions (should appear after 2 seconds)
- Click "Get AI Feedback" button
- Verify suggestions are relevant and helpful

---

## 🔍 Issues to Verify During Demo Prep

### 1. Curriculum Modification Flow
- [ ] Modify button focuses input correctly
- [ ] User can type modification request
- [ ] AI processes modification and regenerates curriculum
- [ ] Modified curriculum displays correctly

### 2. Teaching Topics Generation
- [ ] Teaching topics appear automatically
- [ ] Topics are clickable when ready
- [ ] Clicking topic opens teaching session correctly

### 3. Terminal Claude Code Detection
- [ ] Terminal detects `claude code` commands
- [ ] Backend routes observations correctly
- [ ] AI generates personalized explanations (when implemented)

### 4. Backend Logs
- [ ] No errors in backend logs
- [ ] Context gathering works correctly
- [ ] Exploration history passed correctly
- [ ] Prompt usage is correct

---

## Implementation Priority

### Before Demo (Must Fix):
1. ✅ Document error fix (DONE)
2. ✅ Terminal ANSI sequences fix (DONE)
3. ⚠️ Terminal AI suggestions display (HIGH PRIORITY)
4. ⚠️ Terminal command completion detection (HIGH PRIORITY)

### During Demo Prep (Verify):
1. Curriculum generation and display
2. Context usage in responses
3. Document auto-suggestions
4. Teaching topics functionality

### Nice to Have (Can Fix Later):
1. Enhanced terminal suggestion UI
2. Personalized explanations for terminal activity
3. Better error handling for edge cases

---

## Testing Checklist Before Demo

- [ ] All fixed issues verified working
- [ ] Terminal suggestions display correctly
- [ ] Terminal command completion works
- [ ] Curriculum generation completes successfully
- [ ] Context items are referenced in AI responses
- [ ] Document suggestions work correctly
- [ ] No console errors in browser
- [ ] No backend errors in logs
- [ ] All WebSocket connections stable
- [ ] UI is responsive and smooth

---

## Notes

- Most critical issues are already fixed
- Terminal AI suggestions are the main gap before demo
- Need to implement frontend display and command completion detection
- Other items are verification/testing tasks

