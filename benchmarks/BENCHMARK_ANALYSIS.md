# Benchmark Analysis - January 13, 2026

## Executive Summary

Ran benchmarks with 3 routing configurations. **Anthropic is out of credits** so only Cerebras results are valid. The conversation flow is engaging but **doesn't converge to teaching** - candidates stay at 0.2-0.5 readiness, never reaching 0.7 threshold.

## Provider Status

| Provider | Status | Notes |
|----------|--------|-------|
| **Cerebras** | ✅ Working | ~27s/turn, but doesn't converge well |
| **Anthropic** | ❌ Credit limit | "Your credit balance is too low to access the Anthropic API" |
| **OpenAI GPT-4o-mini** | ✅ Working | **Best performer!** ~13.7s/turn, reaches teaching |

### Updated Results (Jan 13, second run)

| Routing | Time | Turns | Reached Teaching | Topic |
|---------|------|-------|------------------|-------|
| **all_gpt4o_mini** | **68.3s** | **5** | ✅ Yes | "how optimization techniques work in compiler design" |
| all_cerebras_fast | 218.4s | 8 | ❌ No | - |

**Key insight:** GPT-4o-mini converged to a teaching target in 5 turns while Cerebras couldn't after 8 turns.

## Benchmark Results (Jan 13 - Full Run)

### Summary

| Routing | Runs | Reached Teaching | Avg Time | Avg Turns |
|---------|------|------------------|----------|-----------|
| **all_gpt4o_mini** | 1/2 (rate limit) | **1/1 (100%)** | 58.5s | 5.0 |
| all_cerebras_fast | 2/2 | 0/2 (0%) | 190.5s | 8.0 |

### Detailed Results

| Persona | Routing | Time | Turns | Teaching | Topic |
|---------|---------|------|-------|----------|-------|
| mechanism_driven_designer | **all_gpt4o_mini** | **58.5s** | **5** | ✅ | "how different filter types affect sound in synthesizers" |
| mechanism_driven_designer | all_cerebras_fast | 224.6s | 8 | ❌ | - |
| bio_to_policy_switcher | all_cerebras_fast | 156.5s | 8 | ❌ | - |
| bio_to_policy_switcher | all_gpt4o_mini | - | 5 | ⚠️ Rate limited | - |

**Key Finding:** GPT-4o-mini converges to teaching 3.8x faster than Cerebras (58s vs 224s) and actually reaches it!

## Analysis: Why No Teaching Target Reached

### The Cerebras Conversation

**What went well:**
- Questions were contextual and built on user responses
- Identified relevant teaching candidates
- Maintained conversational flow for 8 turns
- Good use of grounded_offer mode

**What didn't work:**
- Teaching candidates stayed too broad (0.2-0.5 readiness)
- Questions circled back to similar themes without narrowing
- Never reached gap identification or scope reduction
- Asked "what about X..." repeatedly without probing deeper

### Teaching Candidates Generated (Final State)

```
- how design principles inform innovative uses of tech in music (readiness: 0.5)
- how interactive visualizations can simplify complex processes (readiness: 0.3)
- how gestural interfaces provide tactile interaction (readiness: 0.4)
- how to make digital interfaces more tactile (readiness: 0.2)
- how gestural interfaces unlock new musical expression (readiness: 0.3)
```

**Problem:** All topics at "hook_identified" stage, none reached "gap_identified" or "scope_reduced".

### Transcript Sample

```
ASSISTANT: Do gestural interfaces in music tech resonate with your design background?
USER: Gestural interfaces are really interesting to me... [shares context]

ASSISTANT: Is the goal to make the digital feel more tactile, or the physical more versatile?
USER: I think it's a bit of both... [shares more context]

ASSISTANT: One thing that's interesting about music tech is... [offers content]
USER: I think the collaborative potential... [engages]

ASSISTANT: Going back to what initially drew you to music tech... [circles back]
```

**Observation:** The conversation is pleasant but doesn't drill down. Each question gets a rich response but the next question often pivots instead of probing the specific gap.

## Root Cause Analysis

1. **LLM isn't following probing depth protocol**
   - Plan specifies: mentioned → hook_identified → model_elicited → gap_identified → scope_reduced
   - Reality: Stays at hook_identified, keeps asking "what about X" questions

2. **Grounded offers don't trigger gap extraction**
   - Offers content but follow-up questions don't probe "what's the specific part you don't understand?"
   
3. **No stakes clarification (U5)**
   - Never asked "why does this matter to you?" or "what would change if you understood this?"

4. **Readiness scoring too conservative**
   - With 5 candidates at 0.2-0.5, should have picked one and probed deeper

## Recommendations

### Immediate Fixes

1. **Add explicit gap-probing questions to controller prompt**
   ```
   IF teaching_candidate.readiness >= 0.4 AND probing_depth < "gap_identified":
       Force question: "What specifically about [topic] is unclear or confusing?"
   ```

2. **Increase readiness scoring for engaged topics**
   - If user keeps returning to a topic, boost its readiness

3. **Add turn-based forcing**
   - After turn 5, if no candidate at 0.7, pick highest and force gap extraction

### Model Routing Recommendations

**Current Best Configuration:**

| Role | Recommended | Reason |
|------|-------------|--------|
| User Simulation | cerebras:llama-3.3-70b | Fast, free |
| Interviewer | openai:gpt-4o-mini | Better convergence |
| Ranker (all tasks) | openai:gpt-4o-mini | Better question quality |

**Alternative - Hybrid for speed:**
- Interviewer: openai:gpt-4o-mini (critical path)
- Ranker bulk tasks: cerebras:llama-3.3-70b (parallel, fast)
- Controller: openai:gpt-4o-mini (smart decisions)

**Once Anthropic credits restored:**
- Test claude-sonnet-4 vs gpt-4o-mini for question quality
- Keep Cerebras for bulk ranker tasks (profile, themes)

## Files Generated

```
benchmarks/results/benchmark_run_jan13/
├── persona_run_mechanism_driven_designer__all_cerebras_fast__7ea3ab1d.json  # Valid
├── persona_run_mechanism_driven_designer__cerebras_claude_interviewer__*.json  # Invalid
├── persona_run_mechanism_driven_designer__all_claude_haiku__*.json  # Invalid
├── benchmark_results.json
└── BENCHMARK_SUMMARY.md
```

## Rate Limits Reference

| Provider | Free Tier | Pro Tier | Notes |
|----------|-----------|----------|-------|
| **Cerebras** | Limited | 50 RPM, 1M TPM | Fast inference causes burst issues |
| **Anthropic** | N/A | Credit-based | **Currently out of credits** |
| **OpenAI** | ~3,500 RPM, 90K TPM | Higher | Most reliable for our use |

**Fix Applied:** Added rate limit detection + longer backoff (5s, 15s, 45s) to `llm_client.py`

## Next Steps

1. [ ] Add credits to Anthropic account
2. [ ] Implement turn-based forcing for gap extraction
3. [ ] Re-run benchmark with fixed prompts
4. [ ] Test hybrid routing (GPT-4o-mini interviewer + Cerebras ranker) when rate limits reset

---

*Generated by run_benchmark_safe.py on 2026-01-13*

