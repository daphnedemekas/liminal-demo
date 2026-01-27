# Terminal AI Suggestions Implementation Plan

## Current Status

### ✅ Backend (Working)
- `TerminalObserver` class processes commands and detects activity types
- Observes terminal commands and outputs
- Detects errors, activity types (claude_code, git, npm, python, etc.), and learning topics
- Routes observations to suggestion router via `route_terminal_observation()`
- Sends observation messages via WebSocket with type `"observation"`

### ❌ Frontend (Incomplete)
- `TerminalTab.tsx` receives observation messages but only logs them to console
- No UI to display AI suggestions to the user
- No way for users to see personalized explanations of terminal activity

## Implementation Tasks

### 1. Frontend: Display Terminal Suggestions
**File**: `frontend/src/components/TerminalTab.tsx`

**Changes needed**:
- Add state for storing AI suggestions/observations
- Display suggestions in a collapsible panel or inline with terminal output
- Show suggestions when `data.type === 'observation'` is received
- Format suggestions nicely (similar to document suggestions)

**UI Options**:
- Option A: Inline suggestions above terminal output (like a banner)
- Option B: Side panel that slides in when suggestions are available
- Option C: Expandable section within terminal tab

**Recommended**: Option A (inline banner) for visibility, with ability to dismiss

### 2. Frontend: Connect to Goal Chat for Personalized Explanations
**File**: `frontend/src/components/TerminalTab.tsx`

**Changes needed**:
- When observation is received, optionally send to goal chat for personalized explanation
- Use existing `onSendToChat` prop pattern (if available) or create new callback
- Format terminal observation as a message that can be sent to chat

### 3. Backend: Generate Personalized Explanations
**File**: `backend/services/suggestion_router.py` or new service

**Changes needed**:
- When routing terminal observation, generate personalized explanation based on:
  - User's learning goal
  - Current teaching topic/task
  - User's prior knowledge and learning style
  - What Claude Code is doing in the terminal
- Use LLM to create contextual explanation
- Send formatted explanation back to frontend

### 4. Backend: Detect Claude Code Activity
**File**: `backend/services/terminal_observer.py`

**Status**: ✅ Already detects `claude_code` activity type
- Patterns: `^claude\s+`, `^claude-code\s+`, `^cc\s+`
- Automatically triggers suggestions for Claude Code interactions

### 5. Frontend: Handle Command Completion
**File**: `frontend/src/components/TerminalTab.tsx`

**Changes needed**:
- Detect when commands complete (currently missing)
- Send `command_complete` message to backend with:
  - Command text
  - Output
  - Exit code
- This triggers observation processing and suggestions

**Implementation approach**:
- Parse terminal output to detect command completion
- Track command start/end
- Send `command_complete` when new prompt appears or command finishes

## Priority Order

1. **High Priority**: Display observations in TerminalTab UI
2. **High Priority**: Send `command_complete` messages to trigger backend processing
3. **Medium Priority**: Generate personalized explanations based on user context
4. **Low Priority**: Enhanced UI for managing multiple suggestions

## Testing Checklist

- [ ] Terminal suggestions appear when Claude Code is used
- [ ] Suggestions appear when errors occur
- [ ] Suggestions appear when learning topics are detected
- [ ] Suggestions are personalized based on user's goal/learning task
- [ ] Suggestions can be dismissed/acknowledged
- [ ] Suggestions can be sent to chat for deeper explanation
- [ ] Command completion detection works correctly
- [ ] Multiple suggestions don't overwhelm the UI

## Notes

- The backend already has most of the infrastructure
- Main gap is frontend display and command completion detection
- Personalized explanations will require integration with discovery/teaching orchestrator

