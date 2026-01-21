# Main

Branch addressing repetitive questioning and feed generation reliability.

## Summary

This branch fixes issues with the ranker agent that could cause repetitive questioning loops, and improves feed generation timeout handling.

## Changes

### Escalation Logic Refactor (`ranker_base.py`)

Extracted escalation decision-making into a single helper function `_build_escalation_response()` that uses unified thresholds:

- **Confidence threshold**: 0.5 (was 0.5 pre-LLM, 0.4 post-LLM)
- **Turns threshold**: 7 (was 8 pre-LLM, 6 post-LLM)

This ensures consistent behavior whether ambiguity is detected pre-LLM or post-LLM.

### Ambiguity Detection (`ranker_base.py:734-744`)

Fixed overly broad pattern matching by using word boundary regex:

```python
# Before: substring match caught "bother" matching "both"
detected_ambiguity = any(pattern in user_message_lower for pattern in ambiguity_patterns)

# After: word boundary regex prevents false positives
ambiguity_patterns = [r"\bboth\b", r"\beither\b", ...]
detected_ambiguity = any(re.search(pattern, user_message_lower) for pattern in ambiguity_patterns)
```

Also removed "any" from patterns since it's too common in legitimate sentences.

### Stuck Pattern Detection (`ranker_base.py:790-814`)

Improved robustness by:

1. Using word stems instead of exact matches ("theor" catches "theory/theoretical")
2. Including more variations ("hands-on", "abstract", "concrete", "real-world")
3. Requiring 3+ matches instead of 2 to reduce false positives

### Code Cleanup

- Removed unused `proposed_action` variable
- Added `asyncio` import at module level in `backend/main.py`
- Removed redundant local `import asyncio` in feed generation

### Feed Generation Timeout (`backend/main.py`)

Increased timeout from 30s to 300s (5 minutes) to allow for LLM client retry logic. Added `max_retries=3` parameter to let the LLM client handle transient failures.

## Testing

Run the backend and verify:

1. Saying "both" or "either" in context (e.g., "I understand both concepts") does not trigger escalation
2. Saying "both" as a deflection ("Both, I guess") does trigger escalation
3. Repeated questioning on the same dimension (theory vs practice) escalates after 3 occurrences
4. Feed generation completes successfully with retries on slow API responses
