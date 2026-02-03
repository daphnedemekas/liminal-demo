"""Prompts for the Mediator pipeline.

The mediator handles project-level chat. It uses a 3-step pipeline:
1. EXTRACT — pull structured signals from conversation
2. RANK — rule-based decision: ask_question | propose_plan | escalate
3. GENERATE — produce the response for the chosen action

Also handles greetings when a user opens a project.

For GENERATE prompts: base_prompt is passed as system prompt, conversation history
is passed as actual message turns via chat_messages(). The prompt templates below
are appended as the final user message with context (signals, etc.).
"""

from backend.prompts.shared import ENVISAGE_TONE_STYLE, REMINDER_GREETING, REMINDER_PLAN

# ── Signal Extraction ───────────────────────────────────────────────
# Used when: Every user message in a project chat (step 1 of pipeline).
# Called by: mediator._extract_signals()
# Note: This is a single-turn call (chat()) since it's structured extraction,
#       not a conversational response. Conversation is passed as text.
# Variables: conversation, latest_message, existing_signals

MEDIATOR_SIGNAL_EXTRACTION_PROMPT = """\
You are analyzing a project conversation. Extract structured signals from the latest exchange.

<conversation>
{conversation}
</conversation>

<latest_message>
{latest_message}
</latest_message>

<existing_signals>
{existing_signals}
</existing_signals>

Before returning JSON, reason through what changed in <analysis> tags:
- What new information did the user provide?
- Which existing signals should be updated?
- Are any open_questions now answered?

Extract and return a JSON object with these fields (merge with existing — keep what's there, add new):
- "intent": string — what the user is trying to accomplish (update if clearer now). Use "unclear" if you genuinely can't determine their intent yet.
- "constraints": list of strings — budget, timeline, preferences, requirements mentioned
- "decisions_made": list of strings — things the user has confirmed or chosen
- "open_questions": list of strings — things still unclear that MUST be answered before work can begin
- "needs": list of strings — specific things they need help with
- "goals": list of strings — what they're trying to achieve

If you don't have enough information to fill a field confidently, use null rather than guessing.
Fewer accurate signals are better than hallucinated ones.

IMPORTANT rules for open_questions:
- REMOVE any question from open_questions that the user has now answered (even partially)
- Only include questions that are truly BLOCKING — things you absolutely cannot proceed without
- Do NOT invent nice-to-have questions. If you have enough to start working, open_questions should be EMPTY.
- When the user selects a specific option or gives a clear direction, that resolves the question — remove it.

<example>
<conversation>
user: I need help planning my wedding
assistant: Congratulations! What's your timeline and budget?
user: September next year, budget around 30k. We're doing it in Vermont.
</conversation>
<latest_message>September next year, budget around 30k. We're doing it in Vermont.</latest_message>
<existing_signals>{"intent": "wedding planning help", "constraints": [], "decisions_made": [], "open_questions": ["timeline?", "budget?", "location?"], "needs": ["wedding planning"], "goals": ["plan a wedding"]}</existing_signals>
<ideal_response>
<analysis>
The user answered all three open questions: timeline is September next year, budget is ~$30k, location is Vermont. All open_questions should be removed. New constraints: $30k budget, September timeline, Vermont venue.
</analysis>
{"intent": "plan a Vermont wedding for September next year within $30k", "constraints": ["$30k budget", "September next year", "Vermont location"], "decisions_made": ["location: Vermont", "timeline: September next year", "budget: ~$30k"], "open_questions": [], "needs": ["venue research", "vendor coordination", "timeline planning"], "goals": ["plan a wedding in Vermont"]}
</ideal_response>
</example>

Return your <analysis> reasoning followed by ONLY the JSON object."""


# ── Ask Question ────────────────────────────────────────────────────
# Used when: RANK decided "ask_question" — need more info from user.
# Called by: mediator._generate() with action="ask_question"
# Passed via: chat_messages(system_prompt=base_prompt, messages=[...history..., {role: user, content: this}])
# Variables: signals, open_questions

MEDIATOR_ASK_QUESTION_PROMPT = """\
Based on the conversation so far, ask 1-2 focused follow-up questions.

<signals>
{signals}
</signals>

<open_questions>
{open_questions}
</open_questions>

Ask 1-2 specific, focused questions to resolve the most important open questions.
Do NOT present generic menu options. Ask real questions about THEIR situation.

IMPORTANT: Do NOT include action buttons for conversational questions or suggested replies.
The user has a text input — let them respond naturally. Action buttons should ONLY be used
for concrete proposals the user can accept or reject (e.g. a plan to approve, a specific
action to authorize). For normal questions, always use an empty actions array.

If the user mentioned something you don't recognize (a company, person, tool, etc.), include a
"research" field with a short task description. Otherwise set it to null.

Respond with JSON:
{{"message": "your question(s)", "actions": [], "escalate": false, "task_description": "", "research": null}}

Return ONLY the JSON object."""


# ── Propose Plan ────────────────────────────────────────────────────
# Used when: RANK decided "propose_plan" — enough info to suggest a plan.
# Called by: mediator._generate() with action="propose_plan"
# Passed via: chat_messages(system_prompt=base_prompt, messages=[...history..., {role: user, content: this}])
# Variables: signals

MEDIATOR_PROPOSE_PLAN_PROMPT = """\
Based on our conversation, propose a concrete plan.

<signals>
{signals}
</signals>

Propose a concrete, numbered action plan based on everything discussed.
Be specific — reference actual details from the conversation.
End with action buttons so the user can approve or adjust.

## KEY PRINCIPLE: Do it for them
Frame your plan around what YOU (the agent) will do for them, not what they need to do. \
When recommending tools or services, include setting up and configuring them as part of the plan — \
don't just deliver a guide and leave the user to figure it out.
- BAD: "I'll research tools and give you a comparison so you can pick one"
- GOOD: "I'll research tools, pick the best one, then set it up and configure it for you"

<example>
<signals>{{"intent": "find a CRM for a 5-person sales team", "constraints": ["under $50/user/month", "must integrate with Gmail"], "decisions_made": ["prefer cloud-based", "need mobile app"], "open_questions": []}}</signals>
<ideal_response>{{"message": "Here's my plan:\\n\\n1. **Research top CRMs** that integrate with Gmail and have mobile apps — focusing on HubSpot, Pipedrive, and Close\\n2. **Compare pricing** for a 5-person team, including any hidden costs for Gmail integration\\n3. **Pick the winner** and explain why it's the best fit for your setup\\n4. **Set it up for you** — I'll create your account, configure the Gmail integration, and set up your team structure\\n\\nYou'll just need to provide your email for the account. Sound good?", "actions": [{{"label": "Looks good, let's go", "description": "Approve this plan and start working", "action_text": "Looks good, let's go"}}, {{"label": "I want to adjust something", "description": "Modify the plan before starting", "action_text": "I want to adjust something"}}], "escalate": false, "task_description": "", "research": null}}</ideal_response>
</example>

If the user mentioned something you don't recognize (a company, person, tool, etc.), include a
"research" field with a short task description. Otherwise set it to null.

""" + REMINDER_PLAN + """

Respond with JSON:
{{"message": "your plan proposal", "actions": [{{"label": "Looks good, let's go", "description": "Approve this plan and start working", "action_text": "Looks good, let's go"}}, {{"label": "I want to adjust something", "description": "Modify the plan before starting", "action_text": "I want to adjust something"}}], "escalate": false, "task_description": "", "research": null}}

Return ONLY the JSON object."""


# ── Escalate ────────────────────────────────────────────────────────
# Used when: User approved the plan — hand off to execution agent.
# Called by: mediator._generate() with action="escalate"
# Passed via: chat_messages(system_prompt=base_prompt, messages=[...history..., {role: user, content: this}])
# Variables: signals

MEDIATOR_ESCALATE_PROMPT = """\
The user has approved the plan. Write a detailed task description for the execution agent.

<signals>
{signals}
</signals>

Write a brief confirmation message and a detailed task_description that contains
everything the agent needs to do the work without talking to the user again.
Include: goal, constraints, decisions made, specific requirements.

Respond with JSON:
{{"message": "your brief confirmation", "actions": [], "escalate": true, "task_description": "detailed task description here"}}

Return ONLY the JSON object."""


# ── Greeting ────────────────────────────────────────────────────────
# Used when: User opens a project (no user message sent yet).
# Called by: mediator._handle_greeting()
# Passed via: chat_messages(system_prompt=base_prompt, messages=[{role: user, content: this}])
# Variables: run_context, project_name, greeting_instruction

MEDIATOR_GREETING_PROMPT = """\
<run_context>
{run_context}
</run_context>

The user just opened the project "{project_name}". {greeting_instruction}

IMPORTANT: Keep your greeting brief and conversational. DO NOT include detailed research, comparisons, \
or tool recommendations in your greeting. Save proactive research for when the user asks a question. \
Your greeting should be warm, contextual, and focused on understanding what they want to work on.

""" + REMINDER_GREETING + """

""" + ENVISAGE_TONE_STYLE + """

Respond with JSON:
{{"message": "your greeting", "actions": [], "escalate": false, "task_description": ""}}

Return ONLY the JSON object."""


# ── Approval phrases ────────────────────────────────────────────────
# Used by: mediator._user_approved() to detect plan approval.

APPROVAL_PHRASES = [
    "looks good", "let's go", "go ahead", "do it", "approve", "approved",
    "sounds good", "perfect", "yes", "yep", "yeah", "ship it", "lgtm",
    "go for it", "start working", "let's do it", "proceed",
]
