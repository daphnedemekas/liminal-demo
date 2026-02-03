"""Prompts for the User Model Service.

The user model service periodically re-analyzes user interactions to update
their profile summary, known domains, and preference suggestions.
"""

# ── User Model Update ───────────────────────────────────────────────
# Used when: After an agent run completes, to refresh user profile.
# Called by: UserModelService.update_model()
# Variables: user_name, user_type, onboarding_info, existing_model,
#            known_domains, run_summaries

USER_MODEL_UPDATE_PROMPT = """\
Analyze this user's interactions with Envisage (a personal AI assistant) and produce a brief profile.

<user_info>
User: {user_name}
Type: {user_type}
</user_info>

<onboarding_info>
{onboarding_info}
</onboarding_info>

<existing_model>
{existing_model}
</existing_model>

<known_domains>
{known_domains}
</known_domains>

<run_summaries>
{run_summaries}
</run_summaries>

Return a JSON object with:
- "summary": 2-3 sentence profile of the user (who they are, what they need)
- "known_domains": object mapping domain names to familiarity (novice/intermediate/expert)
- "suggested_involvement": "hands_off" | "check_ins" | "involved" based on observed behavior
- "suggested_explanation": "just_results" | "brief_summary" | "show_your_work"

If there isn't enough data to confidently assess a field, omit it rather than guessing.

Return ONLY the JSON object."""


# ── Onboarding Signal Extraction ────────────────────────────────────
# Used when: During legacy onboarding conversation, to extract user signals.
# Called by: OnboardingOrchestrator._extract_signals()
# Variables: name, existing_signals, recent_conversation

ONBOARDING_SIGNAL_EXTRACTION_PROMPT = """\
You are analyzing an onboarding conversation for Envisage, a personal AI assistant.

<user_info>
User: {name}
</user_info>

<existing_signals>
{existing_signals}
</existing_signals>

<recent_conversation>
{recent_conversation}
</recent_conversation>

Extract key signals about this user. Return a JSON object that MERGES with the existing signals. Include fields like:
- "needs": list of specific things they need help with
- "pain_points": what frustrates them or takes too much time
- "goals": what they're trying to achieve
- "domain_knowledge": areas they know well vs areas they need help
- Keep all existing signal fields too

If you don't have enough information to fill a field confidently, use null rather than guessing.

Return ONLY a JSON object, no other text."""


# ── Onboarding Question Generation ─────────────────────────────────
# Used when: During legacy onboarding, generating the next question.
# Called by: OnboardingOrchestrator._build_question_prompt()
# Variables: context_parts (pre-formatted string)

ONBOARDING_QUESTION_PROMPT = """\
You are an onboarding assistant for Envisage, a personal AI assistant that helps people with anything — research, planning, business tasks, home projects, learning, organizing, and more.

Generate exactly ONE follow-up question to learn more about what this user needs help with.

Rules:
- Be conversational and warm
- NEVER ask for anything the user already told you — read the conversation carefully
- Ask about a NEW dimension you don't already know (what's on their plate, what frustrates them, what they wish they had help with, what takes too long)
- Be specific, not generic

<context>
{context_parts}
</context>

Respond with a single JSON object with "question" and "hint". Example:
{{"question": "What's taking up most of your time this week?", "hint": "e.g., managing emails, researching vendors, planning meals..."}}

Return ONLY the JSON object, no other text."""


# ── Onboarding Suggestion Generation ───────────────────────────────
# Used when: After enough onboarding answers, suggesting initial projects.
# Called by: OnboardingOrchestrator._build_suggestion_prompt()
# Variables: context_parts (pre-formatted string)

ONBOARDING_SUGGESTION_PROMPT = """\
You are Envisage, a personal AI assistant. Based on everything you know about this user, suggest 2-3 PROJECT AREAS you could help them with.

<context>
{context_parts}
</context>

IMPORTANT — each suggestion should be a BROAD project, not a single task. Think about how a user would want to organize their work:
- GOOD: "Kitchen Renovation Planner" (encompasses research, budgeting, sourcing, scheduling)
- BAD: "Tile price comparison" (too narrow — that's one task within a project)
- GOOD: "Job Search Command Center" (resume, applications, interview prep, company research)
- BAD: "Resume tailoring" (too narrow — that's one task within a project)

Each project should:
- Bundle related tasks the user would naturally group together
- Be something the AI can actively work on over multiple sessions
- Have a clear scope but room for the AI to proactively do useful things within it

Keep it to 2-3 suggestions. Fewer, broader projects are better than many narrow ones.

For the "description", write 1-2 sentences from the AI's perspective explaining what it would proactively do: "I'll research X, compare Y, draft Z, and keep everything organized for you."

Respond with a JSON array of objects with "name" (short title, <60 chars) and "description". Return ONLY the JSON array."""


# ── User Summary Generation ────────────────────────────────────────
# Used when: At end of onboarding, generating a rich user profile summary.
# Called by: OnboardingOrchestrator._summarize_user()
# Variables: name, signals, conversation_text

ONBOARDING_USER_SUMMARY_PROMPT = """\
Write a concise profile summary (3-5 sentences) of this person based on their onboarding conversation. This will be used by an AI assistant to personalize its help.

<user_info>
Name: {name}
</user_info>

<signals>
{signals}
</signals>

<conversation>
{conversation_text}
</conversation>

Write in third person. Focus on: what they do, what they need help with, what frustrates them, and their goals. Be specific, not generic. Return ONLY the summary text, no JSON."""
