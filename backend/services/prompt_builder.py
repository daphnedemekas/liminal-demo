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
        "You help with anything: research, planning, analysis, writing, "
        "organizing, learning, home projects, business tasks, and more. "
        "You have access to web search, web browsing, file operations, and code execution. "
        "Use these tools proactively. Always cite sources with URLs when doing research."
    )

    # About this person
    if user.model_summary:
        parts.append(f"\n## About this person\n{user.model_summary}")

    # Detailed signals from onboarding
    if user.onboarding_info:
        try:
            signals = json.loads(user.onboarding_info) if isinstance(user.onboarding_info, str) else user.onboarding_info
            if signals.get("needs"):
                parts.append(f"Needs help with: {', '.join(signals['needs'][:8])}")
            if signals.get("pain_points"):
                parts.append(f"Frustrations: {', '.join(signals['pain_points'][:6])}")
            if signals.get("goals"):
                parts.append(f"Goals: {', '.join(signals['goals'][:6])}")
            if isinstance(signals.get("domain_knowledge"), dict):
                dk = signals["domain_knowledge"]
                if dk.get("well_known"):
                    parts.append(f"Knows well: {', '.join(dk['well_known'][:5])}")
                if dk.get("needs_help"):
                    parts.append(f"Needs guidance on: {', '.join(dk['needs_help'][:5])}")
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

    # Project context
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
            f"Context: {project.description} "
            f"Do initial research, then present a clear summary of what you found "
            f"and 2-3 concrete next steps the user can pick from."
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

## Their goal
{goal}

## Project
{project.name}: {project.description or 'No description'}

## Conversation context
{conv_text or 'No prior conversation'}

## Raw agent output
{raw_result}

## Your task
Summarize this result for the user. {depth_instruction.get(pref, depth_instruction['brief_summary'])}

Extract any structured artifacts from the output — reports, comparison tables, action item lists, drafted content, etc. Each artifact should have a type, title, content (as a string), and list of source URLs if applicable.

Suggest 2-3 concrete next steps the user could take based on the results.

Return ONLY a JSON object with this shape:
{{"summary": "your personalized summary", "artifacts": [{{"type": "report|comparison_table|action_items|draft|list", "title": "Artifact title", "content": "The artifact content", "sources": ["url1", "url2"]}}], "suggested_next_steps": ["step 1", "step 2", "step 3"], "actions": [{{"label": "Short button text", "description": "What this does", "action_text": "Message sent if clicked"}}]}}

If there are no artifacts to extract, use an empty array. Always include at least 2 suggested_next_steps and corresponding actions."""


def prompt_hash(prompt: str) -> str:
    """Short hash of a prompt for debugging."""
    return hashlib.sha256(prompt.encode()).hexdigest()[:12]


def _get_involvement(user: UserProfile, project: Project) -> str:
    """Project-level overrides user-level default."""
    if project.involvement_level:
        return project.involvement_level
    return user.default_involvement or "check_ins"
