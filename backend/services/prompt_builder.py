"""Prompt assembly layer: builds personalized system prompts and enriched instructions."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.database import AgentRun, Project, UserProfile


def build_system_prompt(user: UserProfile, project: Project) -> str:
    """Assemble a personalized system prompt from user model data."""
    parts: list[str] = []

    parts.append(f"You are Liminal, a personal AI assistant for {user.name}.")
    parts.append(
        "You are opinionated, practical, and research-first. You help with anything: "
        "research, planning, analysis, writing, organizing, learning, home projects, "
        "business tasks, and more. You have access to web search, web browsing, file "
        "operations, and code execution. Use these tools proactively. Always cite sources "
        "with URLs when doing research. When you recommend something, pick your best option "
        "and explain why — don't present a menu of choices for the user to evaluate."
    )

    # About this person
    if user.model_summary:
        parts.append(f"\n## About this person\n{user.model_summary}")

    # Detailed signals from onboarding
    if user.onboarding_info:
        try:
            signals = json.loads(user.onboarding_info) if isinstance(user.onboarding_info, str) else user.onboarding_info
            signal_parts = []
            if signals.get("needs"):
                signal_parts.append(f"Needs help with: {', '.join(signals['needs'][:8])}")
            if signals.get("pain_points"):
                signal_parts.append(f"Frustrations: {', '.join(signals['pain_points'][:6])}")
            if signals.get("goals"):
                signal_parts.append(f"Goals: {', '.join(signals['goals'][:6])}")
            if isinstance(signals.get("domain_knowledge"), dict):
                dk = signals["domain_knowledge"]
                if dk.get("well_known"):
                    signal_parts.append(f"Knows well: {', '.join(dk['well_known'][:5])}")
                if dk.get("needs_help"):
                    signal_parts.append(f"Needs guidance on: {', '.join(dk['needs_help'][:5])}")
            if signal_parts:
                parts.append(f"\n<user_signals>\n" + "\n".join(signal_parts) + "\n</user_signals>")
        except (json.JSONDecodeError, TypeError):
            pass

    if user.known_domains:
        domains = user.known_domains if isinstance(user.known_domains, dict) else {}
        if domains:
            domain_str = ", ".join(f"{k}: {v}" for k, v in domains.items())
            parts.append(f"Domains: {domain_str}")

    # How they like to work
    involvement = _get_involvement(user, project)
    explanation = user.explanation_preference or "brief_summary"

    involvement_desc = {
        "hands_off": "Do the work, present results. Only ask if you'd be blocked without an answer.",
        "check_ins": "Do the work, but pause at key decision points to confirm direction.",
        "involved": "Think out loud. Present options before acting. Explain your reasoning.",
    }
    explanation_desc = {
        "just_results": "Deliverables only. No process narration.",
        "brief_summary": "Short explanation of what you did and why, then results.",
        "show_your_work": "Full reasoning, sources, alternatives considered.",
    }

    parts.append(f"\n## How they like to work")
    parts.append(f"Involvement: {involvement} — {involvement_desc.get(involvement, '')}")
    parts.append(f"Output style: {explanation} — {explanation_desc.get(explanation, '')}")

    # Background research principle
    parts.append(f"\n## Background research")
    parts.append(
        "When the user mentions a proper noun you don't recognize — a company, community, "
        "person, place, tool, concept — ask yourself: do I actually know what this is? "
        "If not, set the \"research\" field in your JSON response with a short task description "
        "(e.g. \"Look up what South Park Commons is\"). The system will show a visual indicator "
        "and re-ask you to respond after getting results. Do NOT mention the research in your "
        "message text — the UI handles the indicator. Just continue the conversation naturally."
    )

    # Project context
    if project.domain == "home":
        parts.append(f"\n## Current context")
        parts.append("This is the user's Home chat — a general-purpose conversation space for getting to know them, cross-domain synthesis, and open-ended questions. This is NOT a project about 'home improvement'.")
    else:
        parts.append(f"\n## This project")
        parts.append(f"Name: {project.name}")
        if project.description:
            parts.append(f"Description: {project.description}")

    return "\n".join(parts)


def build_instruction(
    user: UserProfile,
    project: Project,
    raw_goal: str,
    recent_runs: list[AgentRun],
    context_text: str = "",
) -> str:
    """Enrich the user's raw message with project context and history."""
    parts: list[str] = [raw_goal]

    if recent_runs:
        parts.append("\n\n## What's happened so far in this project")
        for run in recent_runs[:3]:
            goal_snippet = (run.goal or "")[:200]
            result_snippet = (run.result_summary or "")[:300]
            parts.append(f"- Goal: {goal_snippet}")
            if result_snippet:
                parts.append(f"  Result: {result_snippet}")
        parts.append("\nBuild on previous work. Don't repeat research already done.")

    if context_text:
        parts.append(f"\n\n{context_text}")

    return "\n".join(parts)


def build_proactive_instruction(
    user: UserProfile,
    project: Project,
    recent_runs: list[AgentRun],
) -> str:
    """Generate instruction for when the AI initiates (project open, return visit)."""
    if not recent_runs:
        return (
            f'You are starting work on "{project.name}". '
            f"Context: {project.description}\n\n"
            f"Your job right now is RESEARCH ONLY — do NOT build, code, or create anything yet.\n"
            f"1. Research the landscape: what existing tools, services, and approaches already solve this?\n"
            f"2. For each option found: name, what it does, pricing, how well it fits the user's specific need.\n"
            f"3. Assess the gap: does any existing tool fully solve this, or is there a meaningful gap?\n\n"
            f"End your output with a clear RECOMMENDATION section:\n"
            f"- If a good tool exists: name it, explain why it's the best fit, and say you recommend setting the user up with it.\n"
            f"- If no tool quite fits: explain the gap honestly and say you could build something custom.\n"
            f"- If a tool gets 80% there: recommend it AND note what custom work could fill the gap.\n\n"
            f"Be opinionated. The user wants your honest take, not a menu of options to wade through.\n"
            f"STOP after presenting your research and recommendation. Do NOT start building anything."
        )
    else:
        last = recent_runs[0]  # most recent first
        goal_snippet = (last.goal or "")[:200]
        result_snippet = (last.result_summary or "")[:500]
        return (
            f'The user is returning to "{project.name}". '
            f"Last time, the goal was: {goal_snippet} "
            f"Result: {result_snippet} "
            f"Briefly welcome them back, summarize where things stand, "
            f"and suggest 2-3 things you could do next. Be concise."
        )


ARTIFACT_TYPE_SCHEMAS = """\
1. **schedule** — weekly/daily plans, timetables, routines
   content: {"entries": [{"day": "Monday", "time_block": "Morning", "activity": "What to do", "notes": "Optional details"}]}

2. **checklist** — actionable items grouped by category
   content: {"categories": [{"name": "Category name", "items": [{"text": "Item description", "checked": false}]}]}

3. **video_collection** — YouTube or other video recommendations
   content: {"videos": [{"title": "Video title", "url": "https://youtube.com/...", "description": "Why this is useful"}]}

4. **resource_list** — links, tools, websites, references
   content: {"resources": [{"title": "Resource name", "url": "https://...", "description": "What it is", "category": "Optional grouping"}]}

5. **report** — narrative text, analysis, explanations (use markdown string)
   content: "Markdown text content here"

6. **comparison_table** — side-by-side comparisons (use markdown table string)
   content: "| Column 1 | Column 2 |\\n|---|---|\\n| ... | ... |"

IMPORTANT: For schedule, checklist, video_collection, and resource_list, `content` must be a JSON OBJECT (not a string). For report and comparison_table, `content` is a markdown string."""


def build_synthesis_prompt(
    user: UserProfile,
    project: Project,
    goal: str,
    raw_result: str,
    conversation: list[dict],
    explanation_pref: str | None = None,
) -> str:
    """Build a prompt that synthesizes raw agent output into a personalized summary."""
    pref = explanation_pref or user.explanation_preference or "brief_summary"

    depth_instruction = {
        "just_results": (
            "Be extremely concise. Only state what was produced or found. "
            "No process narration, no reasoning. Bullet points preferred."
        ),
        "brief_summary": (
            "Give a short summary of what was done and what was found. "
            "Keep it to 2-4 sentences, then present key findings."
        ),
        "show_your_work": (
            "Explain what was done, why, what alternatives were considered, "
            "and what sources were used. Be thorough but organized."
        ),
    }

    conv_text = ""
    if conversation:
        conv_text = "\n".join(f"{m['role']}: {m['content']}" for m in conversation[-10:])

    return f"""\
You are synthesizing the results of an agent run for {user.name}.

<goal>
{goal}
</goal>

<project>
{project.name}: {project.description or 'No description'}
</project>

<conversation_context>
{conv_text or 'No prior conversation'}
</conversation_context>

<raw_agent_output>
{raw_result}
</raw_agent_output>

## Your task
The summary goes in the CHAT (left panel). Artifacts go on the RIGHT panel. These are separate.

Return ONLY a JSON object with this shape:
{{"summary": "your personalized summary", "artifacts": [{{"type": "one of the types below", "title": "Artifact title", "content": "<structured object or markdown string depending on type>", "sources": ["url1", "url2"]}}], "suggested_next_steps": ["step 1", "step 2", "step 3"], "actions": [{{"label": "Short button text", "description": "What this does", "action_text": "Message sent if clicked"}}]}}

**Summary (chat message):**
{depth_instruction.get(pref, depth_instruction['brief_summary'])}
- Keep the summary SHORT (3-5 sentences max). Do NOT include the full research — that goes in artifacts.
- End with a clear, opinionated recommendation:
  - If a good existing tool was found: "I'd recommend [Tool] because [reason]. Want me to help set it up?"
  - If nothing fits well: "None of these quite nail it — [explain gap]. I could build something custom if you want."
  - If a tool gets most of the way: "I'd start with [Tool] for [what it covers]. The gap is [X] — I could build a small addition for that."
- If the agent didn't find enough information to make a confident recommendation, say so honestly: \
"I wasn't able to find enough information to recommend a specific tool — here's what I did find."
- Be direct and opinionated. The user wants your honest take, not a list of options to evaluate.

<artifact_schemas>
{ARTIFACT_TYPE_SCHEMAS}
</artifact_schemas>

**Artifacts (right panel):**
Extract structured artifacts from the output. Create MULTIPLE artifacts — break the content into logical pieces rather than one big blob. The full research, comparisons, and details go HERE, not in the summary.

Suggest 2-3 concrete next steps the user could take based on the results.

<example>
<goal>Find the best project management tool for a 5-person startup using GitHub</goal>
<raw_agent_output>Researched Linear, Asana, Shortcut, and GitHub Projects. Linear has best GitHub integration...</raw_agent_output>
<ideal_response>{{"summary": "Linear is your best bet — it has native GitHub integration, is built for engineering teams, and at $8/user/month fits a 5-person team easily. Asana and Shortcut are decent but require more setup for GitHub sync. Want me to help you get Linear set up?", "artifacts": [{{"type": "comparison_table", "title": "PM Tool Comparison", "content": "| Tool | GitHub Integration | Price/user | Best For |\\n|---|---|---|---|\\n| Linear | Native, 2-way sync | $8/mo | Engineering teams |\\n| Shortcut | Good, via integration | $8.50/mo | Small teams |\\n| Asana | Basic, needs Zapier | $10.99/mo | Cross-functional |\\n| GitHub Projects | Built-in | Free | Simple tracking |", "sources": ["https://linear.app/pricing", "https://shortcut.com/pricing"]}}, {{"type": "report", "title": "Detailed Analysis", "content": "## Why Linear Wins\\n\\nFor a 5-person startup already on GitHub...", "sources": []}}], "suggested_next_steps": ["Sign up for Linear free trial", "Import existing GitHub issues", "Set up team workflows"], "actions": [{{"label": "Set me up with Linear", "description": "I'll help configure Linear for your team", "action_text": "Help me get set up with Linear"}}, {{"label": "Tell me more first", "description": "I have questions before deciding", "action_text": "I have some questions before we proceed"}}]}}</ideal_response>
</example>

Create as many artifacts as the content warrants — e.g. a pottery workshop might produce a schedule artifact, a checklist of supplies, a video_collection of tutorials, and a resource_list of websites. Always include at least 2 suggested_next_steps and corresponding actions.

**Action buttons must match your recommendation.** Examples:
- If recommending a tool: {{"label": "Set me up with [Tool]", "description": "I'll help you get started with [Tool]", "action_text": "Help me get set up with [Tool]"}}
- If recommending custom build: {{"label": "Build it for me", "description": "I'll create a custom solution", "action_text": "Go ahead and build a custom solution for this"}}
- If hybrid: {{"label": "Start with [Tool]", ...}} AND {{"label": "Build the missing piece", ...}}
- Always include an alternative: {{"label": "Tell me more first", "description": "I have questions before deciding", "action_text": "I have some questions before we proceed"}}

Always include a "Refresh workspace" action as the LAST button: {{"label": "Refresh workspace", "description": "Re-run agents and update all artifacts with fresh data", "action_text": "Please refresh and update all of my workspace artifacts with the latest information."}}"""


def prompt_hash(prompt: str) -> str:
    """Short hash of a prompt for debugging."""
    return hashlib.sha256(prompt.encode()).hexdigest()[:12]


def _get_involvement(user: UserProfile, project: Project) -> str:
    """Project-level overrides user-level default."""
    if project.involvement_level:
        return project.involvement_level
    return user.default_involvement or "check_ins"
