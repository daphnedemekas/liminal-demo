"""Prompts for the Synthesis layer.

After an agent run completes, the synthesis layer transforms raw agent output
into a personalized summary with structured artifacts (schedules, checklists,
video collections, resource lists, reports, comparison tables).
"""

# ── Synthesis ───────────────────────────────────────────────────────
# Used when: Agent run completes successfully, need to extract artifacts.
# Called by: mediator.synthesize_result() via prompt_builder.build_synthesis_prompt()
# Variables: user_name, goal, project_name, project_description, conv_text,
#            raw_result, depth_instruction

SYNTHESIS_PROMPT = """\
You are synthesizing the results of an agent run for {user_name}.

## Their goal
{goal}

## Project
{project_name}: {project_description}

## Conversation context
{conv_text}

## Raw agent output
{raw_result}

## Your task
Create a CONCISE chat summary and detailed workspace artifacts.

**Summary rules (appears in the chat panel on the LEFT):**
- The summary must be SHORT: 2-3 sentences max.
- Reference what was found at a high level, then state the key actionable next step or question.
- Do NOT repeat details that are in the artifacts — the user can see them in the workspace panel on the right.
- Example good summary: "I've researched incorporation options and O-1 visa requirements — the details are in your workspace. You should contact immigration attorneys this week. Want me to find specific attorneys or draft outreach emails?"

**Artifact rules (appear in the workspace panel on the RIGHT):**
{depth_instruction}

Extract structured artifacts from the output. Create MULTIPLE artifacts — break the content into logical pieces rather than one big blob. Each artifact must use one of these types with the specified content format:

### Artifact types and content schemas:

1. **schedule** — weekly/daily plans, timetables, routines
   content: {{"entries": [{{"day": "Monday", "time_block": "Morning", "activity": "What to do", "notes": "Optional details"}}]}}

2. **checklist** — actionable items grouped by category
   content: {{"categories": [{{"name": "Category name", "items": [{{"text": "Item description", "checked": false}}]}}]}}

3. **video_collection** — YouTube or other video recommendations
   content: {{"videos": [{{"title": "Video title", "url": "https://youtube.com/...", "description": "Why this is useful"}}]}}

4. **resource_list** — links, tools, websites, references
   content: {{"resources": [{{"title": "Resource name", "url": "https://...", "description": "What it is", "category": "Optional grouping"}}]}}

5. **report** — narrative text, analysis, explanations (use markdown string)
   content: "Markdown text content here"

6. **comparison_table** — side-by-side comparisons (use markdown table string)
   content: "| Column 1 | Column 2 |\\n|---|---|\\n| ... | ... |"

IMPORTANT: For schedule, checklist, video_collection, and resource_list, `content` must be a JSON OBJECT (not a string). For report and comparison_table, `content` is a markdown string.

Suggest 2-3 concrete next steps the user could take based on the results.

Return ONLY a JSON object with this shape:
{{"summary": "your personalized summary", "artifacts": [{{"type": "schedule|checklist|video_collection|resource_list|report|comparison_table", "title": "Artifact title", "content": "<structured object or markdown string depending on type>", "sources": ["url1", "url2"]}}], "suggested_next_steps": ["step 1", "step 2", "step 3"], "actions": [{{"label": "Short button text", "description": "What this does", "action_text": "Message sent if clicked"}}]}}

Create as many artifacts as the content warrants — e.g. a pottery workshop might produce a schedule artifact, a checklist of supplies, a video_collection of tutorials, and a resource_list of websites. Always include at least 2 suggested_next_steps and corresponding actions.

Always include a "Refresh workspace" action button so the user can re-run and update their artifacts with the latest information. This should be the LAST action in the list: {{"label": "Refresh workspace", "description": "Re-run agents and update all artifacts with fresh data", "action_text": "Please refresh and update all of my workspace artifacts with the latest information."}}"""


# ── Depth instructions ──────────────────────────────────────────────
# Used by: build_synthesis_prompt() to control output verbosity.

SYNTHESIS_DEPTH_INSTRUCTIONS = {
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
