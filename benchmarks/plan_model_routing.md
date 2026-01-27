## Goal
Pick the **best model per call site** (speed × depth × reliability) without brute-forcing an infeasible number of combinations.

This repo has multiple LLM “task types” with different needs:
- **Extraction / updating structured state** (ranker: themes, teaching candidates, profile)
- **Controller planning** (ranker: generate_next_question)
- **User-facing conversation** (interviewer: generate_next_question)
- **Tiny classification** (ranker: branch_condition)

## Why `run_all_benchmarks.py` is a good start (and what it misses)
`benchmarks/run_all_benchmarks.py` currently benchmarks **one simplified theme-extraction prompt** on a single conversation.
That is useful for “raw speed and JSON competence”, but it does **not** measure:
- How well models follow *your real prompts* in `prompts/ranker/*`
- “Preservation requirements” (IDs must be preserved, no dropping)
- Teaching-candidate correctness (strict criteria)
- Controller quality (no explicit topic asking, avoids predictable questions, urgency ramp behavior)
- Interviewer quality (one-question rule, no paraphrasing/echoing, naturalness)
- End-to-end behavior (time-to-teaching-candidate in 5–8 turns)

## A productive evaluation strategy (recommended)

### Phase 0: Sanity + speed baselines (what you already have)
- Run `python3 benchmarks/run_all_benchmarks.py` 3–5 times and compare medians (first call can be cold-start).
- Keep a short list of “candidate fast models” per provider (e.g. Cerebras Llama 3.3 70B, Llama 3.1 8B; OpenAI 4o/4o-mini; Anthropic Haiku/Sonnet).

### Phase 1: Per-call microbenchmarks using *real prompts* (most leverage)
Create microbench tasks that call the **actual code paths** and prompts:
- `RankerAgent._classify_branch_condition`
- `RankerAgent._update_user_profile` (JSON shape correctness)
- `RankerAgent._update_conversational_themes` (ID preservation + concrete-topic extraction)
- `RankerAgent._update_teaching_candidates` (strict criteria adherence)
- `RankerAgent._generate_controller` (policy/constraints + urgency)
- `InterviewerAgent.generate_next_question` (one question, no topic-asking, no paraphrase/echo)

Key idea: **choose the model per task independently first** (you’ll eliminate most of the search space cheaply).

### Phase 2: End-to-end scenario benchmarks (validate interactions)
Use a small suite of fixed “user transcript” scenarios (5–10 scenarios × 6–10 turns):
- User mentions concrete topic early (“backpropagation confusion”)
- User is vague for 2–3 turns then mentions a topic
- User keeps giving preferences; system must pivot to a concrete confusion moment by turn ~5

Metrics:
- **Time per turn** (median/p95)
- **# turns until first teaching candidate** and **until ready_to_teach**
- Constraint violations: asks for topic explicitly, multiple questions, paraphrase/echo

### Phase 3: LLM-as-judge (only after Phase 1/2)
Use one strong model as judge (and optionally a second judge for robustness) to score *qualitative* aspects:
- Did it “open a new frontier” vs ask something answerable from prior text?
- Did it converge appropriately without being pushy?

Important:
- Keep judge prompts extremely specific and **grounded in a rubric**
- Use **pairwise comparisons** (A vs B) rather than absolute 1–10 ratings when possible

### Phase 4: Limited combinatorial sweep (not full factorial)
If you have \(k\) candidates per call site and \(n\) call sites, full search is \(k^n\) (explodes fast).

Instead:
- Pick top 2 per call site from Phase 1 → at most \(2^n\) combos (e.g. 2^6 = 64).
- Run end-to-end scenarios on those 64 combos.
- Optionally do a greedy local search: swap one call site model at a time and keep changes that improve score.

## Practical “default” routing to try first
Based on typical behavior:
- **branch_classifier**: fastest/cheapest that stays accurate (often Cerebras 8B or GPT-4o-mini, or Claude Haiku)
- **themes / teaching_candidates**: models that are very good at structured extraction and instruction-following (Cerebras 70B often wins speed; Sonnet as fallback if criteria violations appear)
- **controller**: higher-quality model if you see constraint failures (topic-asking, repetition, etc.)
- **interviewer**: often needs the most “human” behavior; keep a higher-quality model here if needed

## Implementation note
To sweep many configs in a single process, use `src.config.reset_app_config_cache()` and load different config files per run.







