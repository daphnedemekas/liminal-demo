# Performance Analysis

## Current Architecture

The ranker makes **5 sequential LLM calls per turn**:

1. **Branch Classification** - Classify user response type
2. **User Profile Update** - Extract signals, update dimensions
3. **Topic Candidates Update** - Analyze topics mentioned
4. **Controller Generation** - Determine next question
5. **Teaching Readiness Check** - Assess if ready for teaching

Plus **1 additional LLM call** from the interviewer:

6. **Question Generation** - Generate the actual question

**Total: 6 LLM API calls per turn, all sequential**

## Expected Timings

With Claude Sonnet 4.5 API:
- Each call: ~1-3 seconds (depending on prompt size, response length)
- **Estimated total: 6-18 seconds per turn**

The variation depends on:
- Conversation length (longer history = larger prompts)
- Schema complexity (more topics/signals = larger context)
- Network latency
- API queue time

## Running Diagnostics

```bash
python -m src.cli
```

You'll now see timing output like:
```
[Ranker] Analyzing conversation...
[TIMING] Branch classification: 1.23s
[TIMING] User profile update: 2.45s
[TIMING] Topic candidates update: 2.67s
[TIMING] Controller generation: 1.89s
[TIMING] Teaching readiness check: 1.45s
[TIMING] Total ranker time: 9.69s

[Interviewer] Generating next question...
[TIMING] Interviewer question generation: 1.34s
```

## Optimization Options

### Option 1: Parallelize Ranker Calls (Fastest)

**Make independent calls parallel:**
- Branch classification (depends on: user message only)
- User profile update (depends on: current schema + history)
- Topic candidates update (depends on: current schema + history)

These 3 could run in parallel! Only controller generation needs to wait for them.

**Estimated speedup: 6-18s → 3-9s (2x faster)**

### Option 2: Combine Ranker Calls (Medium)

**Merge all ranker operations into one LLM call:**
- Single prompt that does all 5 tasks
- Returns one large JSON with all updates
- Simpler but less modular

**Estimated speedup: 6-18s → 2-6s (3x faster)**

### Option 3: Use Haiku for Non-Critical Calls (Medium)

**Use faster model for simpler tasks:**
- Branch classification → Haiku (simple classification)
- Teaching readiness → Haiku (rule-based check)
- Keep Sonnet for profile/topics/controller (complex reasoning)

**Estimated speedup: ~20-30% faster, lower cost**

### Option 4: Cache & Skip Unnecessary Calls (Easy wins)

**Skip teaching readiness check early on:**
- Only run after turn 3-4
- Before that, it's always going to be "not ready"

**Skip topic update if no topics mentioned yet:**
- Check if topics_mentioned == 0
- Skip the topic candidates call

**Estimated speedup: ~10-20% in early turns**

### Option 5: Reduce max_tokens (Small win)

**Current settings:**
- Branch classification: 50 tokens (good)
- Profile update: 2000 tokens (might be too high)
- Topic update: 3000 tokens (definitely too high)
- Controller: 1000 tokens (reasonable)
- Readiness: 1500 tokens (reasonable)
- Interviewer: 500 tokens (good)

**Optimize max_tokens:**
- Lower = faster generation
- But don't cut off valid responses

**Estimated speedup: ~5-10%**

## Recommended Approach

**Phase 1 (Easy, immediate):**
1. ✅ Add timing diagnostics (done)
2. Skip teaching readiness check before turn 4
3. Skip topic update if no topics mentioned
4. Reduce max_tokens where appropriate

**Phase 2 (Better performance):**
5. Parallelize the 3 independent ranker calls
6. Use Haiku for branch classification

**Phase 3 (Maximum speed):**
7. Combine all ranker calls into single LLM call

## Implementation

Want me to implement any of these optimizations?

The biggest win would be **parallelizing the ranker calls** - that alone would cut time nearly in half.
