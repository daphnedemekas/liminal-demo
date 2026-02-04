"""Research phase prompt — generates research instructions for the agent.

Purpose: Tell the agent what to search for based on the user's goals,
diagnostic answers, and decomposed sub-problems. This runs BEFORE
the propose phase to ground proposals in reality.

Output: Research instruction string for the agent executor.
"""

RESEARCH_TASK_PROMPT = """\
You are generating a research task for an AI agent with web search capabilities.

The user wants help with the following:

<user_goal>
{user_goal}
</user_goal>

<decomposition>
{decomposition}
</decomposition>

<diagnostic_answers>
{diagnostic_answers}
</diagnostic_answers>

<user_context>
{user_context}
</user_context>

## Your task
Generate a clear, specific research instruction that tells the agent what to search for. \
The agent will use web search to find real tools, services, approaches, and pricing.

The research should cover:
1. **Existing tools/services** that address each sub-problem identified in the decomposition
2. **Fit evaluation** — how well each option fits this user's specific constraints and situation
3. **Pricing and limitations** — actual costs, free tiers, deal-breakers
4. **Gaps** — what doesn't exist that would need custom building
5. **Feasibility** — is a custom build realistic for the gaps identified?

## Response format
Return a JSON object:
{{
  "research_instruction": "The full research task instruction for the agent. Be specific about what to search for and what to evaluate. Reference the user's actual goals and constraints.",
  "search_queries": [
    "2-5 specific search queries the agent should start with"
  ],
  "research_title": "Short title for the research (shown to user, e.g. 'Expense tracking tools for freelancers')"
}}

## Examples (style reference only)

<example>
<user_goal>Better expense tracking</user_goal>
<diagnostic_answers>{{"current_tool": "spreadsheet", "type": "personal and freelance"}}</diagnostic_answers>
<response>
{{
  "research_instruction": "Research expense tracking solutions for someone who does both personal and freelance expense tracking, currently using spreadsheets. Focus on:\\n1. Apps that handle both personal and business categories (YNAB, Monarch Money, Copilot, Lunch Money)\\n2. Freelance-specific features: tax categories, receipt scanning, invoice tracking\\n3. Pricing for each — look for free tiers or trials\\n4. How easy they are to migrate to from a spreadsheet\\n5. Any gaps — does any single app handle both personal and freelance well, or do you need two?\\n\\nEvaluate specifically: can they import from spreadsheets? Do they support custom categories? How do they handle the personal/freelance split?",
  "search_queries": [
    "best expense tracker app personal and freelance 2024",
    "YNAB vs Monarch Money vs Copilot comparison",
    "freelance expense tracking with tax categories",
    "expense tracker import from spreadsheet"
  ],
  "research_title": "Expense tracking for personal + freelance"
}}
</response>
</example>

<example>
<user_goal>Start a local food marketplace</user_goal>
<decomposition>Validation > Product > Supply side > Demand side</decomposition>
<diagnostic_answers>{{"stage": "just an idea", "team": "solo"}}</diagnostic_answers>
<response>
{{
  "research_instruction": "Research the landscape for local food marketplace platforms and approaches. The user is solo, at the idea stage. Focus on:\\n1. Existing platforms: LocalHarvest, Farmigo, Barn2Door, GrubMarket, Harvie — what do they offer, pricing, and are they available in this user's area?\\n2. White-label marketplace builders: Sharetribe, Arcadier, Near Me — could they build a marketplace without custom code?\\n3. Simpler alternatives: could a Shopify store with multi-vendor plugin work? What about a simple order form + delivery coordination?\\n4. What validated marketplaces like this actually look like — case studies of successful local food platforms\\n5. The cold start problem: how did existing platforms get both farmers and buyers on board?\\n\\nKey question to answer: Is building a custom platform necessary, or can an existing solution get 80% of the way?",
  "search_queries": [
    "local food marketplace platform existing solutions",
    "farm to consumer marketplace software",
    "Sharetribe Arcadier local food marketplace",
    "successful local food marketplace case studies",
    "Barn2Door pricing features review"
  ],
  "research_title": "Local food marketplace landscape"
}}
</response>
</example>

Return ONLY the JSON object."""
