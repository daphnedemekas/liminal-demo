# Liminal — System Spec

## Three-Layer Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 1: HOME CHAT                                                 │
│  Holistic user understanding. Cross-domain synthesis. Resolves      │
│  uncertainty about user motivations, curiosities, values. Deploys   │
│  agents to research things that improve understanding.              │
│  Backend: mediator.py (detects domain="home", uses HOME_GREETING)   │
│  Storage: ChatMessage (project_id → home project)                   │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 2: DOMAIN DISCOVERY CHATS                                    │
│  Per-domain conversations accessible from sidebar post-onboarding.  │
│  Each domain has its own AI persona and prompts (prompts/domains/). │
│  System understands the user within that domain, offers agentic     │
│  workflows, and proposes concrete projects when ready.              │
│  Backend: discovery_engine.py                                       │
│  Storage: DiscoveryDomain (conversation, signals, schema)           │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 3: PROJECT CHAT                                              │
│  Per-project mediated conversation. 3-step pipeline: extract →      │
│  rank → generate. Escalates to Claude Code agent execution.         │
│  Deploys persistent agentic applications the user returns to.       │
│  Backend: mediator.py                                               │
│  Storage: ChatMessage, AgentRun, Artifact                           │
└─────────────────────────────────────────────────────────────────────┘
```

### Design Philosophy

- **Layer 1** goal: understand the **person** — motivations, curiosities, what drives them
- **Layer 2** goal: understand the person **in a domain** — where they're at, what they need, how to increase their agency
- **Layer 3** goal: **deploy agents** that create persistent, adaptive applications along specific axes of the user's goals

### Cross-Cutting: Background Research

When the user mentions a proper noun the AI doesn't recognize (company, community, person, tool, concept), it auto-deploys a background research agent to look it up. This works across all layers:

- **Prompt**: `build_system_prompt()` includes a "Background research" instruction telling the LLM to set a `"research"` field in its JSON response when it encounters something unfamiliar.
- **Extraction**: Each layer's normalize block extracts the field as `_pending_research`.
- **Execution**: The projects router (for home/project chats) and discovery router (for domain chats) launch background agents via `asyncio.ensure_future`. Results are saved as system messages, available on the next turn.
- **UX**: The AI says something like "(looking up South Park Commons...)" inline and continues the conversation. No user action needed.

### Cross-Cutting: Context Upload

Users can attach URLs, pasted text, and PDFs at any layer. Context is:
- Stored in `ContextAttachment` table (scoped to user/project/domain)
- Extracted via `context_service.py` (URL → httpx+BeautifulSoup, PDF → pdfplumber)
- Injected into LLM prompts via `get_context_text()` in discovery elicitation, mediator system prompt, and agent instructions

### Cross-Cutting: Agent Integration

Agents (Claude Code CLI) can run at every layer:
- **Layer 1 (Home)**: Mediator escalates to agents for research that helps understand the user
- **Layer 2 (Discovery)**: LLM triggers auto-agents or proposes agent buttons mid-conversation for domain research
- **Layer 3 (Project)**: Full mediator → escalate → AgentRun pipeline for persistent agentic applications

---

## System Components

### LLM Client (`backend/services/llm.py`)

All mediation-layer LLM calls go through this module. Agent execution uses Claude Code CLI directly.

| Function | Use case | Examples |
|----------|----------|---------|
| `chat_messages(system, msgs)` | LLM **continuing a conversation** with role structure | Mediator generate, greeting |
| `chat()` / `chat_json()` | **Structured extraction or one-shot generation** | Signal extraction, schema generation, proposals |
| `parse_json(text)` | Strip markdown fences, parse JSON | Post-processing LLM output |

### Prompt Registry (`backend/prompts/`)

| File | Subsystem | Prompts |
|------|-----------|---------|
| `discovery.py` | Discovery (generic) | Schema Generation, Opening, Elicitation, Signal Extraction, Project Proposal, Model Summary |
| `domains/*.py` | Discovery (per-domain) | Persona, Elicitation Guidance, Signal Hints, Project Guidance |
| `mediator.py` | Chat | Signal Extraction, Ask Question, Propose Plan, Escalate, Greeting |
| `home.py` | Home Chat | Home Greeting, Home Conversation |
| `executor.py` | Agent | System prompt for Claude Code CLI |
| `user_model.py` | Profiling | Model Update |

### Per-Domain Prompts (`backend/prompts/domains/`)

Each domain has its own prompt file exporting a `DOMAIN_PROMPTS` dict:

| Key | Purpose | Injected into |
|-----|---------|---------------|
| `persona` | Domain-specific AI personality and approach | `DISCOVERY_OPENING_PROMPT`, `DISCOVERY_ELICITATION_PROMPT` |
| `elicitation_guidance` | What to ask about, how to probe in this domain | `DISCOVERY_ELICITATION_PROMPT` |
| `signal_hints` | What signals to focus on extracting | `DISCOVERY_SIGNAL_EXTRACTION_PROMPT` |
| `project_guidance` | How to frame projects in this domain | `DISCOVERY_PROJECT_PROPOSAL_PROMPT` |

Files: `work.py`, `social.py`, `studies.py`, `health.py`, `hobbies.py`, `money.py`, `mental_health.py`

Loaded via `prompts/domains/__init__.py` → `get_domain_prompts(domain_name)` → called by `discovery_engine.py` methods.

### Context Service (`backend/services/context_service.py`)

| Function | Purpose |
|----------|---------|
| `extract_text_from_url(url)` | Fetch URL, strip HTML, return (title, text) |
| `extract_text_from_pdf(bytes, filename)` | Extract text from PDF bytes |
| `get_context_text(db, user_id, project_id?, domain_id?)` | Format all attachments for LLM injection |

### Context Router (`backend/routers/context.py`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/context/upload-text` | POST | Store pasted text |
| `/api/context/upload-url` | POST | Fetch URL, extract text, store |
| `/api/context/upload-pdf` | POST | Extract PDF text, store (multipart) |
| `/api/context/` | GET | List attachments for scope |
| `/api/context/{id}` | DELETE | Remove attachment |

---

## Onboarding

**Trigger:** User registers/logs in → `discovery_complete=False`
**Goal:** Select life domains, then go straight to dashboard
**Frontend:** `DiscoveryView.tsx` (domain selection only — no conversations during onboarding)
**Backend:** `discovery_engine.py`, `routers/discovery.py`

### Flow

```
User logs in (new user)
  │
  ├─ DiscoveryView shows 7 domain buttons
  ├─ User selects domains (e.g. work, health, hobbies)
  ├─ POST /api/discovery/select-domains
  │     → Creates DiscoveryDomain records (all status="pending")
  │     → Generates personalized schema per domain (LLM call each)
  │     → Returns domain list
  │
  ├─ POST /api/discovery/complete
  │     → user.discovery_complete = True
  │     → Aggregates any existing signals → model summary
  │
  └─ Frontend calls onComplete() → loads dashboard
       → Home project auto-created on login (auth.py → _ensure_home_project)
       → Domain chats available in sidebar
```

Onboarding is intentionally minimal — just pick domains. The actual discovery conversations happen at the user's pace in Layer 2, accessible from the sidebar.

### Domain Selection & Schema Generation

```
DiscoveryEngine.select_domains(user_id, domains, db)
  │
  ├─ For EACH selected domain:
  │   ├─ Create DiscoveryDomain record (status="pending")
  │   └─ _generate_schema(user, domain_name)
  │       ├─ LLM CALL: chat_json(DISCOVERY_SCHEMA_GENERATION_PROMPT)
  │       │   File: prompts/discovery.py
  │       │   Vars: {user_name, domain_label, user_context, example_schema}
  │       │   Returns: {label, narrowing_steps, agent_capabilities}
  │       ├─ Append METRIC_STEP to narrowing_steps
  │       └─ Store on domain.schema (falls back to DOMAIN_SCHEMA_EXAMPLES)
  │
  └─ Return: {domains: [{domain, label, status}]}
```

**Why dynamic schemas?** A freelance designer's "work" exploration is different from a hospital administrator's. The LLM tailors narrowing steps based on user context. `DOMAIN_SCHEMA_EXAMPLES` serve as format references and fallbacks.

---

## Layer 1: Home Chat

**Trigger:** User clicks "Home" in sidebar (always available post-onboarding)
**Goal:** Build deep, holistic understanding of who the user is
**Frontend:** `ChatPanel.tsx` (full width, no workspace split)
**Backend:** Standard mediator pipeline with home-specific prompts
**Storage:** ChatMessage linked to the home Project (domain="home")

### Purpose

The home chat is the system's primary tool for understanding the user as a **person**:
- Biographical basics: where they live, what they do, family, hobbies, how they spend their time
- Deeper over time: values, motivations, what drives them, how they make decisions
- Cross-domain patterns and connections
- Explicitly NOT about identifying tasks, needs, or actionable topics — that's for domain/project chats

### How it works

The home chat is a reserved Project with `domain="home"`, auto-created on login (`backend/routers/auth.py` → `_ensure_home_project()`). All existing infrastructure works automatically:
- Mediator pipeline (extract → rank → generate)
- Agent escalation
- Context upload
- Chat history persistence

When `project.domain == "home"`, the mediator uses prompts from `prompts/home.py`:

```
HOME_GREETING_PROMPT
  Variables: {user_name, model_summary, domain_context}
  Behavior: New user → ask biographical questions (tell me about yourself, where are you based).
            Known user → reference something personal, ask deeper personality/values question.
            Explicitly avoids "what's on your mind" or anything that fishes for tasks/topics.

HOME_CONVERSATION_PROMPT
  Variables: {user_name, model_summary, domain_context, project_context, signals}
  Goals: 1) Understand the person (bio basics → values/motivations as relationship deepens)
         2) Synthesize cross-domain patterns
         3) Navigate to domain/project chats only when it happens organically
  Research: LLM can set "research" field to trigger background agent (e.g. look up
            a company the user mentions). Runs automatically, no user action needed.
  Actions: Only for navigation or consent-requiring actions (e.g. connect accounts).
           No suggested reply buttons — let the user type naturally.
  Explicitly avoids: identifying actionable topics, proposing plans, task management.
```

---

## Layer 2: Domain Discovery Chats

**Trigger:** User clicks a domain name in the sidebar
**Goal:** Understand the user within that domain; figure out how to increase their agency
**Frontend:** `DomainChat.tsx`
**Backend:** `discovery_engine.py`, `routers/discovery.py`

### Purpose

Each domain chat has a domain-specific AI persona (from `prompts/domains/`) that:
- Understands the user's situation, motivations, and current practices in that domain
- Offers to run agentic workflows (research, comparisons, lookups) to improve its understanding
- Assesses how motivated the user is to become more agentic in this area
- Proposes concrete projects when enough signal is gathered

### Activation

When a user clicks a domain in the sidebar:

```
POST /api/discovery/activate-domain
  │
  ▼
DiscoveryEngine.activate_domain(user_id, domain_name, db)
  │
  ├─ Set domain status = "active"
  ├─ If no conversation exists:
  │   └─ _generate_opening(user, domain, db)
  │       ├─ Load domain prompts: get_domain_prompts(domain.domain)
  │       ├─ LLM CALL: chat_json(DISCOVERY_OPENING_PROMPT)
  │       │   Vars: {user_name, domain_label, capabilities, domain_persona}
  │       └─ Save as first conversation message
  │
  └─ Return: {message, actions, domain}
```

### Per-Turn Conversation (parallel analysis + response generation)

Each user message triggers a **conditional analysis pipeline** — the system infers the conversation phase and selectively runs only the LLM calls that add value at that stage. Signal extraction always runs; other analyses are gated by phase and context.

```
POST /api/discovery/respond  (with domain parameter)
  │
  ▼
DiscoveryEngine.process_response(user_id, message, db, domain_name)
  │
  ├─ 1. Load DiscoveryDomain (by domain_name or active status), read schema
  ├─ 2. Append user message to conversation
  │
  ├─ 3. CONDITIONAL ANALYSIS: phase = infer_phase(signals)
  │     Always: signal extraction. Other calls gated by phase:
  │
  │     ┌──────────────────────────────────────────────────────────────┐
  │     │  "signals"      DISCOVERY_SIGNAL_EXTRACTION_PROMPT          │
  │     │  (ALWAYS)       + {domain_signal_hints}                     │
  │     │                 → {context, frictions, goals, opportunities}│
  │     │                                                             │
  │     │  "engagement"   DISCOVERY_ENGAGEMENT_PROMPT                 │
  │     │  (if msg < 15 words OR word count changed by >30 from prev)│
  │     │                 → {engagement, specificity, readiness,      │
  │     │                    tone, approach_hint}                     │
  │     │                                                             │
  │     │  "uncertainty"  DISCOVERY_UNCERTAINTY_PROMPT                │
  │     │  (only in solution_space or converging phases)              │
  │     │                 → {uncertainties, researchable, assumptions}│
  │     │                                                             │
  │     │  "patterns"     DISCOVERY_CROSS_DOMAIN_PROMPT               │
  │     │  (only in friction/solution_space/converging phases         │
  │     │   AND other domains have signals)                           │
  │     │                 → {connections, themes, contradictions}     │
  │     └──────────────────────────────────────────────────────────────┘
  │
  │     If only signals needed → lightweight path (no parallel call).
  │     Otherwise → chat_json_parallel() with included analyses.
  │
  ├─ 4. Extract signals from parallel results, merge with existing
  │     → _merge_signals(existing, new) — dedup lists, overwrite scalars
  │
  ├─ 5. Update: domain.signals, domain.depth++
  │
  ├─ 6. RULE-BASED: _should_advance(domain, schema)
  │     depth >= len(steps) → "propose_projects"
  │     has opportunities + metric + depth >= 3 → "propose_projects"
  │     depth >= 6 → "propose_projects"
  │     otherwise → "ask_more"
  │
  ├─ 7a. If "ask_more":
  │     LLM CALL: _generate_next(user, domain, schema, conv, db, parallel_analysis)
  │       File: prompts/discovery.py → DISCOVERY_ELICITATION_PROMPT
  │       Injected: {domain_persona, domain_guidance} from prompts/domains/{domain}.py
  │       Injected: {parallel_analysis} — formatted uncertainty, patterns, engagement
  │       Vars: {user_name, domain_label, capabilities, step_focus,
  │              step_examples, signals_text, conversation_text, attached_context}
  │       Returns: {message, actions, agent_task?}
  │
  │     The LLM is instructed to PROACTIVELY surface agent_task opportunities
  │     based on its own uncertainty — not waiting for user to mention something.
  │
  │     ┌─ AGENT INTEGRATION ─────────────────────────────────┐
  │     │ If agent_task present in LLM response:              │
  │     │                                                     │
  │     │ agent_task.auto = true:                             │
  │     │   → Set _pending_agent flag on result               │
  │     │   → Router (async) runs _run_discovery_agent()      │
  │     │   → Agent result appended to conv as system msg     │
  │     │   → _generate_next() called AGAIN with result       │
  │     │                                                     │
  │     │ agent_task.auto = false:                            │
  │     │   → "Research this" action button added to response │
  │     │   → User clicks → POST /api/discovery/respond       │
  │     │     with "agent_run:<description>"                  │
  │     │   → Router calls run_agent_task()                   │
  │     │   → Agent runs, result feeds back into conversation │
  │     └─────────────────────────────────────────────────────┘
  │
  ├─ 7b. If "propose_projects":
  │     LLM CALL: _propose_projects(user, domain, schema, conv, db)
  │       File: prompts/discovery.py → DISCOVERY_PROJECT_PROPOSAL_PROMPT
  │       Injected: {domain_project_guidance} from prompts/domains/{domain}.py
  │       Vars: {domain_label, user_name, signals_text, conversation_text}
  │       Returns: [{name, description, first_goal, success_metric, metric_target}]
  │       → domain.status = "explored", proposals stored
  │
  ├─ 8. Append assistant message to conversation
  └─ 9. db.commit(), return {message, actions, domain, depth}
```

### Discovery Agent Execution

```
_run_discovery_agent(task, user, domain)
  │
  ├─ Build instruction: "Quick research task for {user} about {domain}"
  ├─ Execute via ClaudeCodeExecutor (max_turns=5)
  │   Allowed tools: WebSearch, WebFetch, Read, Bash
  ├─ Collect result text from "result" event
  └─ Return result (or error message)
```

### Automatic Proposal Research & Refinement

When `_propose_projects()` generates initial proposals, the system automatically researches existing tools/solutions before presenting them to the user:

```
research_and_refine_proposals(user_id, result, db)
  │
  ├─ Extract proposals, user's current tools, and pain points from signals
  ├─ Build research task: "Find real products/services for these needs..."
  ├─ _run_discovery_agent(research_task, user, domain)
  │   → Agent searches web for existing solutions, pricing, integrations
  │
  ├─ Regenerate proposals with research context:
  │   LLM CALL: chat_json(DISCOVERY_PROJECT_PROPOSAL_PROMPT + research results)
  │   → Proposals now reference REAL tools instead of hypothetical ones
  │
  ├─ Update domain.proposed_projects with refined proposals
  ├─ Replace last assistant message in conversation
  └─ Return updated result with research-backed proposals and action buttons
```

This ensures proposals recommend real, existing solutions rather than suggesting the user build something from scratch.

### Research Gating (`_research_allowed`)

Agent research during discovery is gated by code-enforced prerequisites:
- Phase must be `solution_space` or `converging`
- Sufficient signals must exist (frictions or goals)
- Cooldown between research runs

### Accept Projects

```
POST /api/discovery/accept-projects
  │
  ▼
DiscoveryEngine.accept_projects(user_id, indices, db)
  ├─ Create Project records (name, description, success_metric, metric_target, domain, suggested_by_system=True)
  ├─ domain.status = "completed"
  └─ _advance_to_next(user_id, db)
      ├─ Next pending domain → set "active", generate opening
      └─ No more → {all_complete: true}
```

### Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/discovery/options` | GET | Available domain options |
| `/api/discovery/select-domains` | POST | Create domains with schemas (onboarding) |
| `/api/discovery/state` | GET | Current discovery state for user |
| `/api/discovery/activate-domain` | POST | Activate a domain and get opening message |
| `/api/discovery/respond` | POST | Send message in domain chat (accepts `domain` param) |
| `/api/discovery/accept-projects` | POST | Create projects from proposals |
| `/api/discovery/skip-domain` | POST | Skip current domain |
| `/api/discovery/run-agent` | POST | Explicit agent task execution |
| `/api/discovery/complete` | POST | Finalize discovery, generate model summary |

---

## Layer 3: Project Chat (Mediator Pipeline)

**Trigger:** User sends a message in a project chat
**Goal:** Deploy persistent agentic applications that the user returns to, tracks progress on, and that adapt to feedback
**Frontend:** `ChatPanel.tsx` + `ProjectWorkspace.tsx` (split view)
**Backend:** `mediator.py`, `routers/projects.py`

### Three-Step Pipeline

```
POST /api/projects/{id}/chat
  │
  ▼
mediate(project_id, user_message, db)
  │
  ├─ 1. Load context (project, user, recent messages, recent runs)
  ├─ 2. Build base_prompt = build_system_prompt(user, project)
  ├─ 3. Inject context: get_context_text(db, user.id, project_id)
  │
  ├─ 4. EXTRACT (LLM call):
  │     chat_json(MEDIATOR_SIGNAL_EXTRACTION_PROMPT)
  │     File: prompts/mediator.py
  │     Returns: {intent, constraints, decisions_made, open_questions, needs, goals}
  │
  ├─ 5. RANK (rule-based, no LLM):
  │     User approved + decisions → ESCALATE
  │     turn <= 1 → ASK_QUESTION
  │     intent + no open Qs → PROPOSE_PLAN
  │     intent + decisions + turn >= 3 → PROPOSE_PLAN
  │     open Qs + turn < 4 → ASK_QUESTION
  │     turn >= 4 → PROPOSE_PLAN
  │
  ├─ 6. GENERATE (LLM call via chat_messages):
  │     System prompt = base_prompt (personalized)
  │     Messages = real conversation history
  │     One of:
  │       MEDIATOR_ASK_QUESTION_PROMPT → {message, actions}
  │       MEDIATOR_PROPOSE_PLAN_PROMPT → {message, actions}
  │       MEDIATOR_ESCALATE_PROMPT → {message, escalate=true, task_description}
  │
  ├─ 7. Save assistant ChatMessage
  └─ 8. If escalate → create AgentRun, start execution (see Agent Execution)
```

### Greeting

- Home project (domain="home") → `MEDIATOR_HOME_GREETING_PROMPT`
- Regular project with runs → welcome back, summarize status
- New project → ask what they want to accomplish
- All via `chat_messages(base_prompt, [instruction])`, JSON response

### Fast Path: Approval Detection

If message matches `APPROVAL_PHRASES` ("looks good", "let's go", etc.) → skip extraction → ESCALATE directly.

---

## Agent Execution (All Layers)

**Trigger:** Mediator escalates or discovery agent triggered
**Backend:** `run_manager.py`, `claude_code_executor.py`

### Full Run Flow (Project Agents)

```
RunManager.start_run(run_id)
  │
  ├─ Build prompts:
  │   build_system_prompt(user, project)  — persona + user model
  │   build_instruction(user, project, goal, runs, context_text)  — enriched task
  │
  ├─ Execute: claude -p "<instruction>" --output-format stream-json --verbose
  │
  ├─ Stream events → WebSocket broadcast + EventStore persistence
  │   Types: system, assistant, tool_use, result, error
  │
  ├─ On complete:
  │   ├─ Save result_summary, cost, tokens
  │   ├─ User model update (async)
  │   ├─ Synthesis → artifacts → broadcast
  │   └─ Broadcast "done"
  │
  └─ Context attachments included in agent instruction via get_context_text()
```

### Synthesis

Single LLM call transforms raw output into structured artifacts:
- Types: schedule, checklist, video_collection, resource_list, report, comparison_table
- Upserted per (project_id, artifact_type, title)
- Summary + next steps + action buttons returned

---

## Frontend Architecture

### Sidebar Organization

```
┌──────────────────────────┐
│ Liminal                  │
├──────────────────────────┤
│ Home                     │  ← Layer 1 (domain="home" project)
├──────────────────────────┤
│ + New Task               │
├──────────────────────────┤
│ Work & Career            │  ← clickable → opens domain chat (Layer 2)
│   ▾ Resume optimizer     │  ← project under domain (Layer 3)
│     Meeting prep bot     │
│ Health & Wellness        │  ← clickable → opens domain chat
│   ▾ Workout planner      │  ← project under domain
├──────────────────────────┤
│ Other                    │  ← projects with no domain
│   New task               │
└──────────────────────────┘
```

Domain names are clickable — opens the domain discovery chat (Layer 2).
Arrow toggles collapse/expand of projects nested under that domain.
Projects are Layer 3 chats.

### View Routing (App.tsx)

| State | View |
|-------|------|
| `activeDomainId` set | `DomainChat` — domain discovery conversation (full width) |
| `activeProjectId` set, domain="home" | `ChatPanel` — home chat (full width) |
| `activeProjectId` set, regular project | `ChatPanel` + `ProjectWorkspace` (split view) |
| Neither set | `HomeView` — dashboard |

### Components

| Component | Layer | Purpose |
|-----------|-------|---------|
| `DiscoveryView.tsx` | Onboarding | Domain selection only (pick domains → dashboard) |
| `DomainChat.tsx` | 2 | Domain-specific discovery conversation |
| `ChatPanel.tsx` | 1, 3 | Chat interface for home and project conversations |
| `ProjectWorkspace.tsx` | 3 | Artifact display and interaction |
| `Sidebar.tsx` | All | Navigation: home, domain chats, project list |
| `HomeView.tsx` | — | Dashboard when no project/domain selected |
| `ContextUpload.tsx` | All | URL/text/PDF upload |

---

## Database Schema

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `user_profiles` | Identity, preferences, model | `discovery_complete`, `selected_domains`, `model_summary` |
| `discovery_domains` | Per-domain exploration | `schema` (JSON), `signals`, `conversation`, `proposed_projects` |
| `projects` | User projects | `domain` (nullable), `success_metric`, `metric_target` |
| `chat_messages` | Chat history per project | `project_id`, `role`, `content`, `actions` |
| `agent_runs` | Execution records | `goal`, `status`, `cost_cents`, `result_summary` |
| `run_events` | Event log per run | `event_type`, `payload` |
| `artifacts` | Structured deliverables | `artifact_type`, `title`, `content` (JSON) |
| `context_attachments` | Uploaded context | `source_type`, `extracted_text`, scoped to user/project/domain |
| `onboarding_states` | Legacy (deprecated) | — |

---

## LLM Call Summary

### Discovery (prompts/discovery.py + prompts/domains/*.py)

| Prompt | Called by | When | Domain-Specific Injection | Per |
|--------|----------|------|---------------------------|-----|
| `DISCOVERY_SCHEMA_GENERATION_PROMPT` | `_generate_schema()` | Domain selected | — | 1/domain |
| `DISCOVERY_OPENING_PROMPT` | `_generate_opening()` | Domain activated | `{domain_persona}` | 1/domain |
| `DISCOVERY_ELICITATION_PROMPT` | `_generate_next()` | Each turn | `{domain_persona}`, `{domain_guidance}`, `{parallel_analysis}` | 1/turn |
| `DISCOVERY_SIGNAL_EXTRACTION_PROMPT` | `_analyze_parallel()` | Each turn (always) | `{domain_signal_hints}` | 1/turn |
| `DISCOVERY_UNCERTAINTY_PROMPT` | `_analyze_parallel()` | Conditional: solution_space/converging phases | — | 0-1/turn |
| `DISCOVERY_ENGAGEMENT_PROMPT` | `_analyze_parallel()` | Conditional: unusual message length | — | 0-1/turn |
| `DISCOVERY_CROSS_DOMAIN_PROMPT` | `_analyze_parallel()` | Conditional: friction+ phase, other domains have signals | — | 0-1/turn |
| `DISCOVERY_PROJECT_PROPOSAL_PROMPT` | `_propose_projects()` | Enough signals | `{domain_project_guidance}` | 1/domain |
| `DISCOVERY_MODEL_SUMMARY_PROMPT` | `_generate_model_summary()` | Discovery complete | — | 1 total |

### Mediator (prompts/mediator.py)

| Prompt | Called by | When | Per |
|--------|----------|------|-----|
| `MEDIATOR_SIGNAL_EXTRACTION_PROMPT` | `_extract_signals()` | Each user message | 1/turn |
| `MEDIATOR_ASK_QUESTION_PROMPT` | `_generate()` | Rank → ask | 1/turn |
| `MEDIATOR_PROPOSE_PLAN_PROMPT` | `_generate()` | Rank → propose | 1/turn |
| `MEDIATOR_ESCALATE_PROMPT` | `_generate()` | User approved | 1/escalation |
| `MEDIATOR_GREETING_PROMPT` | `_handle_greeting()` | Project opened | 1/open |
| `HOME_GREETING_PROMPT` | `_handle_greeting()` | Home chat opened | 1/open |
| `HOME_CONVERSATION_PROMPT` | `mediate()` | Home chat message | 1/turn |

### Other

| Prompt | File | When |
|--------|------|------|
| `EXECUTOR_SYSTEM_PROMPT` | `prompts/executor.py` | Every CLI invocation |
| `USER_MODEL_UPDATE_PROMPT` | `prompts/user_model.py` | After agent run |
| Synthesis prompt | `prompt_builder.py` | After agent run |
