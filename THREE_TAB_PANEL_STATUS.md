# Three-Tab Panel System Status

## Overview

The three-tab panel system is a feature designed to enhance the Goal Chat interface with three additional panels:
1. **Context Tab** - Store and manage context items (text, files, images, code)
2. **Draft Tab** - Create and edit documents (essays, applications, code, notes)
3. **Terminal Tab** - Interactive terminal sessions for hands-on learning

## Current Status

### ✅ Backend Implementation (Complete)

The backend has full API support for all three tabs:

#### Context Tab APIs
- `POST /api/goal/{goal_id}/context` - Add text context
- `GET /api/goal/{goal_id}/contexts` - Get all context items
- `PUT /api/goal/{goal_id}/context/{context_id}` - Update context item
- `DELETE /api/goal/{goal_id}/context/{context_id}` - Delete context item

#### Draft Tab APIs
- `POST /api/goal/{goal_id}/document` - Create document
- `GET /api/goal/{goal_id}/documents` - Get all documents
- `GET /api/document/{document_id}` - Get specific document
- `PUT /api/document/{document_id}` - Update document
- `PUT /api/document/{document_id}/config` - Update suggestion config
- WebSocket: `/ws/document/{document_id}` - Real-time document sync and suggestions

#### Terminal Tab APIs
- `POST /api/terminal/start` - Start terminal session
- `GET /api/terminal/{session_id}/history` - Get command history
- WebSocket: `/ws/terminal/{session_id}` - Interactive terminal

#### Chat Channels (Related Feature)
- `POST /api/goal/{goal_id}/channel` - Create chat channel
- `GET /api/goal/{goal_id}/channels` - Get all channels
- `PUT /api/channel/{channel_id}/context` - Update channel context
- `GET /api/channel/{channel_id}/messages` - Get channel messages
- WebSocket: `/ws/channel/{channel_id}` - Channel chat with AI suggestions

### ❌ Frontend Implementation (Missing)

**No frontend components exist yet for the three-tab panel system.**

The following components need to be created:

1. **Tab Navigation Component**
   - Tab switcher UI (Context | Draft | Terminal)
   - Integration into GoalChat component

2. **ContextTab Component** (`frontend/src/components/ContextTab.tsx`)
   - List of context items
   - Add text context (textarea + submit)
   - File upload support
   - Delete/edit context items
   - Display context items with type badges

3. **DraftTab Component** (`frontend/src/components/DraftTab.tsx`)
   - Document list/selector
   - Rich text editor (or markdown editor)
   - Document creation modal
   - Suggestion config UI
   - WebSocket integration for real-time sync

4. **TerminalTab Component** (`frontend/src/components/TerminalTab.tsx`)
   - Terminal emulator (xterm.js or similar)
   - Command input
   - Output display
   - WebSocket integration for PTY

5. **Integration into GoalChat**
   - Add tab navigation to GoalChat layout
   - Show/hide tabs based on state
   - Pass panel context to prompt system

## Backend Files Reference

### Database Models
- `src/database/models.py`:
  - `GoalContext` (line 215) - Context tab items
  - `GoalDocument` (line 250) - Draft tab documents
  - `TerminalSession` (line 291) - Terminal tab sessions
  - `ChatChannel` (line 323) - Chat channels

### API Endpoints
- `backend/main.py`:
  - Context Tab: lines 2045-2104
  - Draft Tab: lines 2106-2180
  - Terminal Tab: lines 2182-2217
  - Chat Channels: lines 2219-2278
  - WebSockets: lines 2280-2620

### Schema Definitions
- `src/schema/panel_context.py` - All Pydantic models for panel context

### Prompt Integration
- `src/prompt/gather.py`:
  - `gather_context_items()` (line 159) - Gather from Context tab
  - `gather_document_context()` (line 204) - Gather from Draft tab
  - `gather_terminal_observation()` (line 241) - Gather from Terminal tab

- `src/prompt/components.py` (line 58-60):
  - `goal_context_items` - Context tab items
  - `active_document` - Draft tab document
  - `terminal_observation` - Terminal tab observation

## Database Schema

The database automatically creates these tables:
- `goal_contexts` - Context items
- `goal_documents` - Documents
- `terminal_sessions` - Terminal sessions
- `chat_channels` - Chat channels
- `channel_messages` - Channel messages

## How It Works (Backend)

1. **Context Tab**: Users can add text snippets, upload files, or paste code. These are stored and made available to the LLM when generating responses.

2. **Draft Tab**: Users can create documents (essays, code, notes). The AI can provide suggestions based on the document content. Documents sync in real-time via WebSocket.

3. **Terminal Tab**: Users can run terminal commands. The AI observes terminal activity and can provide suggestions in bound chat channels (e.g., "Sandbox Suggestions" channel).

4. **Chat Channels**: Each goal has multiple chat channels:
   - "Main Chat" - General conversation
   - "Sandbox Suggestions" - Bound to terminal, provides suggestions based on terminal activity
   - "Draft Feedback" - Bound to document, provides feedback on drafts
   - Custom channels - User-created channels with custom suggestion contexts

## Next Steps to Implement Frontend

1. **Create Tab Navigation**
   ```tsx
   // In GoalChat.tsx
   const [activeTab, setActiveTab] = useState<'chat' | 'context' | 'draft' | 'terminal'>('chat')
   ```

2. **Create ContextTab Component**
   - Use API endpoints: `/api/goal/{goal_id}/context*`
   - Display list of context items
   - Add/delete functionality

3. **Create DraftTab Component**
   - Use API endpoints: `/api/goal/{goal_id}/document*`
   - Integrate rich text editor (e.g., TipTap, Lexical, or simple textarea)
   - WebSocket: `/ws/document/{document_id}` for real-time sync

4. **Create TerminalTab Component**
   - Use xterm.js or similar terminal emulator
   - WebSocket: `/ws/terminal/{session_id}` for PTY connection
   - Display command history

5. **Update GoalChat Layout**
   - Add tab navigation bar
   - Conditionally render tabs
   - Maintain chat as primary view

## Example API Usage

### Context Tab
```typescript
// Add text context
await fetch(`/api/goal/${goalId}/context`, {
  method: 'POST',
  body: JSON.stringify({
    goal_id: goalId,
    user_id: userId,
    text_content: "Important note about the project",
    content_type: "text"
  })
})

// Get all contexts
const contexts = await fetch(`/api/goal/${goalId}/contexts`)
```

### Draft Tab
```typescript
// Create document
await fetch(`/api/goal/${goalId}/document`, {
  method: 'POST',
  body: JSON.stringify({
    goal_id: goalId,
    user_id: userId,
    title: "My Essay",
    document_type: "essay",
    plain_text: "Essay content here..."
  })
})
```

### Terminal Tab
```typescript
// Start terminal
const terminal = await fetch('/api/terminal/start', {
  method: 'POST',
  body: JSON.stringify({
    goal_id: goalId,
    user_id: userId,
    working_directory: "~"
  })
})

// Connect via WebSocket
const ws = new WebSocket(`ws://localhost:8000/ws/terminal/${terminal.session_id}`)
```

## Related Documentation

- Backend API endpoints: `backend/main.py` lines 1933-2620
- Database models: `src/database/models.py`
- Schema definitions: `src/schema/panel_context.py`
- Prompt integration: `src/prompt/gather.py`



