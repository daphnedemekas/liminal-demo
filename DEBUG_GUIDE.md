# Debug and Inspection Guide

## Enhanced Debug Modes

### Basic Debug Mode
Shows comprehensive schema state after each turn:

```bash
python -m src.cli --debug
```

**What it shows:**
- **Interview State**: Turn count, topics mentioned, confidence scores
- **User Profile**: All dimensions with confidence scores
  - Curiosity type (interest/deprivation) with evidence
  - Entry mode (people/problems/ideas scores)
  - Uncertainty tolerance
  - Motivation profile (intrinsic/utility/identity values)
  - RIASEC hints
  - Pacing preference
- **Signals Extracted**: Last 3 signals with evidence quotes
- **Topic Candidates**: All topics with:
  - Readiness scores
  - Probing depth (mentioned → hook_identified → model_elicited → gap_identified → scope_reduced)
  - Hook type (mechanism/meaning/beauty/utility)
  - RPL fit (too_easy/proximal/too_hard)
  - Identified gaps
  - Value scores
- **Controller State**: Next action, question intent, branch condition, suggested question
- **Teaching Readiness**: When ready, shows target topic, focus question, angle, first move

### Verbose Mode
Shows everything in debug mode PLUS the full raw JSON schema:

```bash
python -m src.cli --debug --verbose
```

**What it adds:**
- Complete JSON dump of entire schema
- All nested objects fully expanded
- Useful for inspecting exact data structures

### Combined with User ID
Persistent profile across sessions:

```bash
python -m src.cli --user-id my-user-123 --debug
```

This loads the user's profile from previous sessions and shows how it evolves.

## Database Inspection

### View What's Stored
Inspect the SQLite database contents:

```bash
python inspect_db.py
```

**What it shows:**
- All users in the database
- For each user:
  - User ID and metadata
  - Full profile dimensions (as stored in DB)
  - All conversation sessions
  - Session details (turns, topics, final topic)
  - Last schema state for each session
  - All signals extracted with evidence
  - Total sessions and topics explored

### What Gets Saved to Database

**Per Turn:**
1. **Full Schema State** → `conversation_sessions.schema_state` (JSON)
   - Complete snapshot of entire discovery schema
   - All topic candidates
   - All signals
   - Interview state
   - Controller state
   - Teaching recommendation

2. **User Profile** → `user_profiles` table
   - `curiosity_type`: {value, confidence, evidence[]}
   - `entry_mode`: {people, problems, ideas scores}
   - `uncertainty_tolerance`: {value, confidence, evidence[]}
   - `interest_phase_default`: {value, confidence, notes}
   - `motivation_profile`: {intrinsic, utility, identity, cost}
   - `pacing_preference`: {value, confidence}
   - `riasec_hint`: {I, A, S, R, E, C scores}
   - `communication_style`: {verbosity, complexity, emotional_expression, question_asking_frequency}

**Per Session:**
- Session metadata in `conversation_sessions` table
  - Session ID, user ID
  - Start/end timestamps
  - Turn count
  - Topics mentioned count
  - Final topic (if reached teaching phase)

**Signals** (if implemented):
- Individual signals in `signals` table
  - Turn number, type, evidence quote
  - Interpretation, updates_field, confidence
  - Linked to user and session

## Understanding the Output

### Confidence Scores
- `0.0-0.3`: Low confidence, tentative signal
- `0.3-0.6`: Moderate confidence, some evidence
- `0.6-0.8`: High confidence, clear pattern
- `0.8-1.0`: Very high confidence, strong evidence

### Readiness Scores (Topics)
- `0.0-0.3`: Just mentioned, barely explored
- `0.3-0.6`: Some exploration, not ready
- `0.6-0.8`: Well explored, approaching ready
- `0.8-1.0`: Highly ready for teaching

### Probing Depth (Topics)
- `mentioned`: Just came up in conversation
- `hook_identified`: We know what aspect attracts them
- `model_elicited`: We know their current understanding
- `gap_identified`: We know their specific confusion
- `scope_reduced`: Narrowed to 5-minute learning target

### RPL Fit (Topics)
- `too_easy`: They already know this
- `proximal`: Perfect difficulty - on verge of understanding (ideal!)
- `too_hard`: Way beyond current knowledge
- `unknown`: Can't assess yet

### Branch Conditions
- `topic_mentioned`: User named a specific topic
- `personal_shared`: User shared context/feelings
- `deflection`: User avoided or said "I don't know"
- `preference_signal`: User expressed learning preference
- `question_asked`: User asked a question
- `unclear`: Doesn't fit other categories

## Debug Logging

The system now prints these during operation:

```
[Ranker] Analyzing conversation...
[DB] Saving session state...
[DB] Updating user profile in database...
[DB] Profile updated for user 1a2b3c4d...
[Orchestrator] Ready for teaching phase!
[Interviewer] Generating next question...
```

This shows the flow:
1. Ranker analyzes user's response
2. Database saves full schema state
3. Database updates user profile
4. Orchestrator checks teaching readiness
5. Interviewer generates next question

## Example Debug Output

```
═══════════ Schema State ═══════════
Turn: 3
Topics Mentioned: 1
Confidence in Profile: 0.45
Confidence in Target: 0.70

User Profile:
  Curiosity Type: mixed (conf: 0.60)
    Evidence: "if its analytical it feels an itch, especially if i feel...
  Entry Mode: people=0.20, problems=0.70, ideas=0.80
  Uncertainty Tolerance: medium (conf: 0.55)
  Motivation: intrinsic=0.60, utility=0.75, identity=0.80
  RIASEC: I=0.30, A=0.40, S=0.60
  Pacing: exploratory

Signals Extracted (2):
  - Turn 1: preference_signal (conf: 0.70)
    "something that aligns with how i can make impact, positively on the wo...
  - Turn 2: value (conf: 0.80)
    "as well as something deep and profound about reality"

Topic Candidates (1):
  - difference between 'I should be interested in this' and truly being interested
    Readiness: 0.90 | Probing: gap_identified
    Hook: meaning | RPL Fit: proximal
    Gap: Understanding the phenomenology of authentic vs imposed curiosity
    Values: intrinsic=0.90, utility=0.70

Controller:
  Next Action: probe_topic
  Question Intent: extract_gap
  Branch Condition: personal_shared
  Suggested Question: When you notice that difference between "should" and genuine intere...

═══════════════════════════════════
```

## Tips

1. **Start with --debug** for readable summary
2. **Add --verbose** only when you need raw JSON
3. **Use --user-id** to track learning over time
4. **Run inspect_db.py** to see what persists between sessions
5. **Watch the [DB] logs** to confirm data is being saved

## Troubleshooting

**Schema not updating?**
- Check for [ERROR] messages in output
- Run with --verbose to see raw schema
- Check inspect_db.py to verify DB writes

**Profile not persisting?**
- Verify user_id is same across runs
- Check `data/liminal.db` exists
- Run inspect_db.py to see stored profiles

**Want even more detail?**
- Set `echo=True` in `config.yaml` database section to see SQL queries
- Add print statements in `src/agents/ranker.py` for LLM responses
