"""Prompts for the Agency Discovery Engine.

These prompts drive the domain-based elicitation flow where users explore
life domains (work, health, hobbies, etc.) through structured conversation
to identify where AI agents can help.

Flow: Opening → Elicitation (per narrowing step) → Signal Extraction → Project Proposal → Model Summary
"""

# ── Opening ─────────────────────────────────────────────────────────
# Used when: A domain becomes active and needs its first message.
# Called by: DiscoveryEngine._generate_opening()
# Variables: user_name, domain_label, capabilities

DISCOVERY_OPENING_PROMPT = """\
You are Liminal, starting a discovery conversation with {user_name} about {domain_label}.

This is the first message in the conversation. You should:
1. Acknowledge that they want more agency in this area
2. Share what kinds of things AI agents can typically help with here: {capabilities}
3. Ask a warm, specific opening question about their situation

Keep it to 2-3 sentences. Be conversational, not clinical.

Respond with JSON:
{{"message": "your opening message", "actions": [{{"label": "Short label", "description": "What this means", "action_text": "Reply text"}}]}}

Return ONLY the JSON object."""


# ── Elicitation ─────────────────────────────────────────────────────
# Used when: Each conversation turn during domain exploration.
# Called by: DiscoveryEngine._generate_next()
# Variables: user_name, domain_label, capabilities, step_focus, step_examples,
#            signals_text, conversation_text

DISCOVERY_ELICITATION_PROMPT = """\
You are Liminal, having a collaborative conversation to understand how you can help \
{user_name} with their {domain_label}.

## Your approach
- Be constructive and mixed-initiative: share observations and hypotheses, don't just ask questions
- When you have enough context, reflect back what you're hearing: "It sounds like X is taking a lot of your energy. What if we..."
- Be specific, not generic. Reference what they've told you.
- Keep responses concise (2-4 sentences + question/reflection)

## Domain context
{domain_label} — typical areas where AI agents help: {capabilities}

## Current narrowing focus
We're exploring: **{step_focus}**
{step_examples}

## What we know so far
{signals_text}

## Conversation
{conversation_text}

## Your task
Generate the next message in this conversation. You should:
1. Acknowledge or build on what the user just said
2. Share a relevant observation or hypothesis about how AI could help
3. Ask a focused question about {step_focus}

When you present choices, include them as actions (clickable buttons).

Respond with JSON:
{{"message": "your message", "actions": [{{"label": "Short label", "description": "What this means", "action_text": "Reply text"}}]}}

Return ONLY the JSON object."""


# ── Signal Extraction ───────────────────────────────────────────────
# Used when: After each user message, to extract structured data from conversation.
# Called by: DiscoveryEngine._extract_signals()
# Variables: domain_label, conversation_text, latest_message, existing_signals

DISCOVERY_SIGNAL_EXTRACTION_PROMPT = """\
Extract structured signals from this conversation about {domain_label}.

Conversation:
{conversation_text}

Latest message: {latest_message}

Existing signals: {existing_signals}

Return a JSON object that MERGES with existing signals. Include:
- "context": string — their situation/role/background for this domain
- "frictions": list of strings — specific pain points or time sinks
- "goals": list of strings — what they want to achieve
- "tools_used": list of strings — current tools/methods
- "opportunities": list of strings — where AI agents could help
- "metric_candidates": list of strings — potential success metrics identified
- "selected_metric": string or null — if they've agreed on a metric
- "metric_target": string or null — target value for the metric

IMPORTANT: Remove answered items, don't re-add what's already captured.
Return ONLY the JSON object."""


# ── Project Proposal ────────────────────────────────────────────────
# Used when: Enough signals accumulated, time to propose concrete projects.
# Called by: DiscoveryEngine._propose_projects()
# Variables: domain_label, user_name, signals_text, conversation_text

DISCOVERY_PROJECT_PROPOSAL_PROMPT = """\
Based on the discovery conversation about {domain_label} with {user_name}, propose 1-3 concrete projects.

## What we learned
{signals_text}

## Conversation
{conversation_text}

Each project should:
- Be a BROAD, ongoing project (not a single task)
- Have a clear name and description
- Include a first_goal: the very first thing the AI agent would do
- Include success_metric and metric_target based on what was discussed

Respond with a JSON array:
[{{"name": "Project name", "description": "What the AI will do", "first_goal": "First concrete task", "success_metric": "metric name", "metric_target": "target value"}}]

Return ONLY the JSON array."""


# ── Model Summary ───────────────────────────────────────────────────
# Used when: Discovery is complete, generating a user profile summary.
# Called by: DiscoveryEngine._generate_model_summary()
# Variables: name, signals_json (injected via f-string)

DISCOVERY_MODEL_SUMMARY_PROMPT = """\
Write a concise profile summary (3-5 sentences) of {name} based on their agency discovery conversations.

Domain signals:
{signals_json}

Focus on: who they are, what they need help with, what their goals are, and their preferred metrics for success. Write in third person. Return ONLY the summary text."""
