# Envisage — System Architecture

## Overview

Envisage is a personal AI companion that builds deep understanding of who you are, then interaactively deploys agents to help across all areas of your life.

```
┌─────────────────────────────────────────────────────────────────────┐
│  HOME CHAT                                                          │
│  Get to know the person. Biographical basics → values/motivations.  │
│  Cross-domain synthesis. Background research on unfamiliar topics.  │
│  Routes to domain chats when conversations get specific.            │
│  Backend: home.py                                                   │
├─────────────────────────────────────────────────────────────────────┤
│  DOMAIN DISCOVERY CHATS                                             │
│  Per-domain conversations (work, health, hobbies, etc).             │
│  Domain-specific AI personas. Agent research mid-conversation.      │
│  Proposes concrete projects when ready.                             │
│  Backend: discovery_engine.py                                       │
├─────────────────────────────────────────────────────────────────────┤
│  PROJECT CHAT                                                       │
│  Per-project mediated conversation with agent execution.            │
│  Extract → Rank → Generate pipeline. Synthesis creates artifacts.   │
│  Split view: chat on left, workspace artifacts on right.            │
│  Backend: mediator.py                                               │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Principles

1. **Understand the person first** — Home chat builds holistic understanding before jumping to tasks
2. **Domain-specific depth** — Each life domain has tailored prompts and personas
3. **Agent-first execution** — Claude Code CLI runs real tasks with web search, file ops, code execution
4. **Structured artifacts** — Agent output is synthesized into schedules, checklists, reports, etc.
5. **Background research** — Auto-deploys agents when AI encounters unfamiliar topics

---

## Home Chat

**Purpose:** Build deep understanding of who the user is as a person.

**Backend:** `backend/services/home.py`

**Prompts:** `backend/prompts/home.py`

### Flow

```
User opens Home
  │
  ├─ First time: "Hey! Where are you based, what do you do for work, and what do you like to do for fun?"
  │
  ├─ Returning user: Reference something personal, ask deeper question
  │
  ├─ Each message:
  │   ├─ Extract signals (fast model)
  │   ├─ Check for navigation suggestion (if 3+ turns on specific topic)
  │   ├─ Generate curious response (get to know them)
  │   └─ If unfamiliar proper noun → background research agent
  │
  └─ May suggest navigating to domain chat when topic gets specific
```

### Navigation Routing

The home chat monitors conversations and may suggest moving to a domain chat when:
1. Conversation focuses on ONE specific life area for 3+ turns
2. User is seeking concrete help (not just describing something)
3. That area maps to a domain the user selected during onboarding

**Critical:** Routing is based on what the user is trying to GET HELP WITH, not keyword matching. Describing their AI startup means "work", not "mental health" even if they mention mental health as a product feature.

---

## Domain Discovery Chats

**Purpose:** Understand the user within a specific life domain; figure out how to increase their agency.

**Backend:** `backend/services/discovery_engine.py`, `backend/routers/discovery.py`

**Prompts:** `backend/prompts/discovery.py`, `backend/prompts/domains/*.py`

### Per-Domain Personas

Each domain has its own prompt file in `backend/prompts/domains/`:
- `work.py`, `social.py`, `studies.py`, `health.py`, `hobbies.py`, `money.py`, `mental_health.py`

These provide:
- `persona` — Domain-specific AI personality
- `elicitation_guidance` — What questions to ask
- `signal_hints` — What to extract from responses
- `project_guidance` — How to frame project proposals

### Flow

```
User clicks domain in sidebar
  │
  ├─ Activate domain, generate opening message
  │
  ├─ Each message:
  │   ├─ Signal extraction (always)
  │   ├─ Conditional analysis (engagement, uncertainty, cross-domain patterns)
  │   ├─ May trigger auto-agent for research
  │   └─ Generate next question or propose projects
  │
  ├─ When enough signals gathered:
  │   ├─ Research existing tools/solutions
  │   └─ Propose concrete projects with real recommendations
  │
  └─ User accepts projects → creates Project records
```

### Agent Integration

Agents can run mid-discovery for research:
- **Auto-agents:** LLM decides to research something → runs automatically
- **Button agents:** "Research this" button → user clicks to trigger
- Results feed back into conversation for better understanding

---

## Project Chat

**Purpose:** Deploy persistent agentic workflows the user returns to.

**Backend:** `backend/services/mediator.py`, `backend/routers/projects.py`

**Prompts:** `backend/prompts/mediator.py`

### Extract → Rank → Generate Pipeline

```
User sends message
  │
  ├─ EXTRACT (LLM): Parse intent, constraints, decisions, open questions
  │
  ├─ RANK (rules):
  │   ├─ User approved plan → ESCALATE
  │   ├─ Early turn, unclear intent → ASK_QUESTION
  │   ├─ Clear intent, no blockers → PROPOSE_PLAN
  │   └─ User confirmed plan → ESCALATE
  │
  ├─ GENERATE (LLM): Produce response based on rank decision
  │   ├─ ASK_QUESTION: Clarifying question
  │   ├─ PROPOSE_PLAN: "Here's what I'll do..." with approve button
  │   └─ ESCALATE: Create AgentRun, start execution
  │
  └─ If escalate → Agent runs → Synthesis → Artifacts
```

### Synthesis

After agent completes, synthesis transforms raw output into:
- **Chat summary:** 2-3 sentences with key actionable
- **Workspace artifacts:** Schedules, checklists, reports, comparisons, resource lists

Artifacts appear in the right panel workspace.

---

## Agent Execution

**Backend:** `backend/services/run_manager.py`, `backend/services/claude_code_executor.py`

### Flow

```
RunManager.start_run(run_id)
  │
  ├─ Build personalized system prompt + instruction
  │
  ├─ Execute: claude -p "<instruction>" --output-format stream-json
  │
  ├─ Stream events via WebSocket:
  │   ├─ assistant (text output)
  │   ├─ tool_use (what tools being called)
  │   ├─ result (final output)
  │   └─ error (if failed)
  │
  ├─ On complete:
  │   ├─ Synthesis → create artifacts
  │   ├─ Broadcast synthesis event
  │   └─ Broadcast "done" status
  │
  └─ Artifacts committed to DB before broadcast
```

### Orphan Cleanup

On backend startup, any runs stuck in "working" status are marked as failed. This handles cases where the backend was restarted while runs were in progress.

---

## Background Research

Works across all layers. When the AI encounters an unfamiliar proper noun:

1. LLM sets `"research": "Look up what X is"` in response
2. Router detects this and spawns background agent
3. Agent runs (web search, etc.)
4. Results saved as system message
5. LLM re-generates response with research context
6. UI shows subtle "Researching..." indicator

---

## Context Upload

Users can attach context at any layer:
- **URLs** — Fetched and text extracted
- **Pasted text** — Stored directly
- **PDFs** — Text extracted via pdfplumber

Context is injected into LLM prompts and agent instructions.

**Backend:** `backend/services/context_service.py`, `backend/routers/context.py`

---

## Frontend Architecture

### View Routing

| State | View |
|-------|------|
| Domain selected | `DomainChat` — full width |
| Home project | `ChatPanel` — full width |
| Regular project | `ChatPanel` + `ProjectWorkspace` — split view |
| Nothing selected | `HomeView` — dashboard |

### Key Components

| Component | Purpose |
|-----------|---------|
| `Sidebar.tsx` | Navigation: home, domains, projects |
| `ChatPanel.tsx` | Chat interface (home + projects) |
| `DomainChat.tsx` | Domain discovery conversations |
| `ProjectWorkspace.tsx` | Artifact display |
| `HomeView.tsx` | Dashboard |
| `ContextUpload.tsx` | URL/text/PDF upload |

---

## Database Schema

| Table | Purpose |
|-------|---------|
| `user_profiles` | User identity, preferences, model summary |
| `discovery_domains` | Per-domain state: schema, signals, conversation |
| `projects` | User projects with optional domain association |
| `chat_messages` | Chat history per project |
| `agent_runs` | Execution records: goal, status, result, cost |
| `run_events` | Event log per run |
| `artifacts` | Structured deliverables (schedules, checklists, etc.) |
| `context_attachments` | Uploaded context scoped to user/project/domain |
| `user_insights` | Extracted insights for memory retrieval |

---

## API Endpoints

### Auth
- `POST /api/auth/login` — Login/register
- `GET /api/auth/me` — Current user

### Projects
- `GET /api/projects/` — List projects
- `POST /api/projects/` — Create project
- `POST /api/projects/{id}/chat` — Chat (SSE stream)
- `GET /api/projects/{id}/artifacts` — Get artifacts

### Runs
- `POST /api/runs` — Create run
- `GET /api/runs/{id}` — Get run details
- `GET /api/runs/active/{project_id}` — Get active run for project
- `POST /api/runs/{id}/stop` — Stop run
- `WS /ws/run/{run_id}` — WebSocket for run events

### Discovery
- `GET /api/discovery/options` — Available domains
- `POST /api/discovery/select-domains` — Select domains (onboarding)
- `POST /api/discovery/activate-domain` — Activate domain chat
- `POST /api/discovery/respond` — Send message in domain chat
- `POST /api/discovery/accept-projects` — Accept proposed projects

### Context
- `POST /api/context/upload-url` — Upload URL
- `POST /api/context/upload-text` — Upload text
- `POST /api/context/upload-pdf` — Upload PDF
- `GET /api/context/` — List attachments

### Insights
- `GET /api/insights/{user_id}` — Get user insights

---

## LLM Models

| Model | Use Case |
|-------|----------|
| `gpt-4o` | Main generation (mediator, discovery responses) |
| `gpt-4o-mini` | Fast extraction (signals, routing checks) |
| Claude Code CLI | Agent execution (with web search, file ops) |

---

## Key Files

| File | Purpose |
|------|---------|
| `backend/services/home.py` | Home chat logic |
| `backend/services/mediator.py` | Project chat pipeline |
| `backend/services/discovery_engine.py` | Domain discovery |
| `backend/services/run_manager.py` | Agent execution lifecycle |
| `backend/services/claude_code_executor.py` | CLI wrapper |
| `backend/services/llm.py` | OpenAI client |
| `backend/services/memory.py` | Insight extraction/retrieval |
| `backend/prompts/home.py` | Home chat prompts |
| `backend/prompts/mediator.py` | Project chat prompts |
| `backend/prompts/discovery.py` | Discovery prompts |
| `backend/prompts/synthesis.py` | Artifact synthesis prompt |
| `backend/prompts/domains/*.py` | Per-domain personas |
