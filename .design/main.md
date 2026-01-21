# Main

Uncommitted changes addressing repetitive questioning and feed generation reliability.

## Review

**Verdict:** Needs work

### Issues

1. **Ambiguity detection is overly broad** (`ranker_base.py:688-695`)

   The pattern list catches legitimate responses:
   ```python
   ambiguity_patterns = [
       "both", "either", "all of", ...
   ]
   ```
   "Both" in "I understand both concepts" or "either" in "I'd prefer either approach works" are not deflections. The substring matching (`pattern in user_message_lower`) has no word boundary check - "I like to bother with details" triggers on "both".

2. **Duplicate escalation logic** (`ranker_base.py:698-724` and `750-769`)

   The pre-LLM ambiguity handler and the post-LLM intent-repetition handler both escalate to `propose_task_curriculum` or `grounded_offer` using nearly identical code. If ambiguity is detected pre-LLM, the function returns early - but if it's not detected, the post-LLM handler can still trigger the same escalation. The conditions overlap (`assessment_confidence >= 0.5` vs `>= 0.4`, `turns >= 8` vs `>= 6`).

3. **Stuck pattern detection is fragile** (`ranker_base.py:779-783`)

   The hardcoded keyword groups:
   ```python
   stuck_keywords = [
       ("theory", "practice", "application"),
       ("historical", "practical", "context"),
       ("concepts", "examples", "applications")
   ]
   ```
   These assume specific phrasing. "hands-on vs abstract" or "practical experience" won't match. The 2-of-3 match threshold can trigger on unrelated uses of common words.

4. **Import inside try block** (`backend/main.py:714`)

   `import asyncio` is inside the try block but asyncio is already available at module level (used elsewhere in the file). Minor, but unnecessary.

5. **Unused variable** (`ranker_base.py:743`)

   `proposed_action = response.get("next_action", "")` is assigned but never read.

### What works

- The timeout wrapper for feed generation (`backend/main.py:716-726`) is a reasonable safeguard against hanging LLM calls.
- The grounded_offer prompt additions give clear guidance for making recommendations instead of asking preference questions.
- The forward progress principles in the controller prompt articulate the escalation ladder well.

## Design notes

The changes address a real problem: the conversation can loop on the same dimension (theory vs practice, etc.) when users give non-committal answers. The solution has two parts:

1. **Pre-LLM short-circuit**: Pattern-match ambiguous responses and skip the LLM call entirely
2. **Post-LLM override**: If LLM suggests a repeated intent, escalate instead

The intent is sound but implementation conflates detection (identifying ambiguity) with action (choosing escalation). A cleaner approach would separate these: detect ambiguity/repetition in one place, then have a single escalation decision tree that considers both signals together.
