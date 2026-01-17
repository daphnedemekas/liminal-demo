# Research-Based Curiosity Discovery System

## Overview

This is a complete redesign of the curiosity discovery system based on cognitive science research frameworks. The system conducts natural conversations to identify what users are genuinely curious about, then identifies their specific "Region of Proximal Learning" (RPL) for effective teaching.

## Research Foundations

The system is grounded in:

- **Litman's I-Type vs D-Type Curiosity**: Interest-driven (novelty) vs deprivation-driven (gap filling)
- **Zone of Proximal Development (ZPD)**: Vygotsky's framework for optimal learning difficulty
- **RIASEC Model**: Interest texture (Investigative/Artistic/Realistic-Social)
- **Four-Phase Interest Development**: From triggered to well-developed interest (Hidi & Renninger)
- **Productive vs Hopeless Confusion**: Identifying generative struggle vs demotivating frustration
- **Self-Determination Theory**: Autonomy, competence, relatedness as motivation drivers
- **Expectancy-Value Theory**: Intrinsic value, utility value, identity value, and perceived cost

## Architecture

```
┌─────────────────────────────────────────┐
│           User Session                   │
│  (tracked via user_id, persists)        │
└──────────────┬──────────────────────────┘
               │
               ↓
┌─────────────────────────────────────────┐
│        Orchestration Layer              │
│  • Load user profile from DB            │
│  • Load modular prompts                 │
│  • Coordinate Interviewer + Ranker      │
└──────────────┬──────────────────────────┘
               │
          ┌────┴────┐
          ↓         ↓
┌──────────────┐  ┌──────────────┐
│ Interviewer  │  │   Ranker     │
│ - Asks       │  │ - Analyzes   │
│   questions  │  │ - Updates    │
│ - Natural    │  │   schema     │
│   convo      │  │ - Classifies │
└──────────────┘  └──────────────┘
          │         │
          └────┬────┘
               ↓
┌─────────────────────────────────────────┐
│          SQLite Database                │
│  • User profiles (persistent)           │
│  • Conversation sessions                │
│  • Signals extracted                    │
└─────────────────────────────────────────┘
```

## File Structure

```
liminal-demo/
├── prompts/
│   ├── background_resources.txt       # Research concept definitions
│   ├── interviewer/                   # Modular interviewer prompts
│   │   ├── base.txt                   # Core role and principles
│   │   ├── opening.txt                # Opening question bank
│   │   ├── topic_probing.txt          # 5-step topic exploration
│   │   ├── relevance_bridge.txt       # Personal context handling
│   │   ├── scaffolding.txt            # Deflection/uncertainty support
│   │   ├── profile_update.txt         # Learning preference signals
│   │   ├── clarification.txt          # User question handling
│   │   ├── general_continuation.txt   # Default flow
│   │   └── transition_to_teach.txt    # Teaching phase handoff
│   └── ranker/                        # Ranker analysis prompts
│       ├── update_user_profile.txt    # Profile dimension tracking
│       ├── update_topic_candidates.txt # Topic analysis
│       ├── generate_next_question.txt  # Controller logic
│       └── check_readiness.txt        # Teaching readiness
│
├── src/
│   ├── schema/
│   │   └── full_schema.py             # Pydantic models (20+ dimensions)
│   ├── database/
│   │   ├── models.py                  # SQLAlchemy models
│   │   └── manager.py                 # Database operations
│   ├── agents/
│   │   ├── interviewer.py             # Conversational agent
│   │   ├── ranker.py                  # Cognitive architect
│   │   └── orchestrator.py            # Coordination
│   ├── background_resources.py        # Resource injection
│   ├── prompt_loader.py               # Modular prompt loading
│   ├── llm_client.py                  # Claude API wrapper
│   └── cli.py                         # Command-line interface
│
├── data/
│   └── liminal.db                     # SQLite database (created automatically)
│
├── requirements.txt
├── config.yaml
└── README_RESEARCH_SYSTEM.md          # This file
```

## Key Features

### 1. Background Resources System
- Central repository of research concept definitions
- Automatic injection into prompts via `[CONCEPT_NAME]` placeholders
- Example: `[FRICTION_PROBE]` → "Where does your understanding stop feeling crisp?"

### 2. Modular Prompt System
- Prompts adapt based on branch conditions:
  - `topic_mentioned`: Run topic probing sequence
  - `personal_shared`: Build relevance bridge
  - `deflection`: Provide scaffolding and reduce cost
  - `preference_signal`: Adapt to learning style
  - `question_asked`: Answer and return to discovery
  - `unclear`: General continuation

### 3. Rich User Profiling (20+ Dimensions)
Tracks across sessions:
- Curiosity type (interest vs deprivation)
- Entry mode (people, problems, ideas)
- Uncertainty tolerance
- Interest phase default
- Motivation profile (intrinsic, utility, identity, cost)
- Pacing preference (fast resolution vs exploratory)
- RIASEC hints (I, A, S, R, E, C)
- Communication style

### 4. Topic Probing Sequence (5 steps)
1. **Accept**: Validate their choice
2. **Disambiguate Hook**: Mechanism, meaning, beauty, utility?
3. **Elicit Current Model**: What do they already know?
4. **Extract Gap**: Where's the confusion? (uses question strategies)
5. **Shrink Scope**: Convert to 5-minute learning target

### 5. Multi-Session Memory
- User profiles persist across conversations
- Accumulative learning about user preferences
- Session history tracking

### 6. Teaching Readiness Detection
Automatically determines when to transition based on:
- Topic specificity (medium/specific)
- Gap identification (concrete confusion identified)
- RPL fit (within Zone of Proximal Development)
- Value clarity (why it matters to user)
- Confidence thresholds
- Probing depth (gap identified or scope reduced)

## Usage

### Basic Usage

```bash
# Run the discovery system
python -m src.cli

# With persistent user profile
python -m src.cli --user-id your-user-id

# With debug mode (shows schema state)
python -m src.cli --debug
```

### Example Conversation Flow

1. **Opening**: "What have you been curious about lately?"
2. **User mentions topic**: "I've been thinking about quantum entanglement"
3. **Disambiguate hook**: "What about it caught your interest?"
4. **User explains**: "I don't understand how it doesn't violate relativity"
5. **Extract gap**: "Where does your understanding stop feeling crisp?"
6. **User clarifies**: "I get that particles are correlated, but I don't get why it doesn't allow FTL communication"
7. **Scope reduction**: "If we could make one thing click in 5 minutes, what would it be?"
8. **User focuses**: "Why can't we use entanglement to send information faster than light?"
9. **System**: Ready for teaching! Topic identified within RPL.

## Schema Overview

The complete `DiscoverySchema` includes:

```python
{
  "session_id": str,
  "user_profile": {
    "curiosity_type": {value, confidence, evidence[]},
    "entry_mode": {people, problems, ideas},
    "uncertainty_tolerance": {value, confidence, evidence[]},
    # ... 20+ total dimensions
  },
  "signals": [
    {turn, type, evidence_quote, interpretation, updates_field, confidence}
  ],
  "topic_candidates": [
    {
      id, topic_seed, disambiguated_hook, user_phase,
      current_model_summary, identified_gap, specificity,
      estimated_RPL_fit, values{}, probing_depth,
      readiness_score, confusion_type, ...
    }
  ],
  "interview_state": {
    turns_elapsed, dimensions_explored, topics_mentioned,
    confidence_in_profile, confidence_in_target,
    ready_for_teach_phase
  },
  "controller": {
    next_action, next_question, question_intent,
    fallback_questions[], branch_condition
  },
  "teaching_recommendation": {
    ready, target_topic, focus_question, angle,
    difficulty_calibration, format, pacing, first_move
  }
}
```

## Ranker Agent (Cognitive Architect)

The ranker performs 5 LLM calls per turn:

1. **Classify Branch Condition**: What type of response did user give?
2. **Update User Profile**: Extract signals about curiosity type, pacing, etc.
3. **Update Topic Candidates**: Track topics mentioned, identify gaps
4. **Generate Controller**: Determine next action and question
5. **Check Readiness**: Assess if ready for teaching phase

## Question Strategies

Research-grounded question types:

- **[FRICTION_PROBE]**: "Where does your understanding stop feeling crisp?"
- **[COMPRESSION_TEST]**: "Give me your best 20-second explanation, even if wrong"
- **[BOUNDARY_QUESTION]**: "What would you need to know to feel like you understood this?"
- **[COUNTERFACTUAL_HOOK]**: "If you understood this, what would change?"
- **[IDENTITY_PROBE]**: "Is this connected to something you're trying to become?"
- **[DEFLECTION_RESPONSE]**: Normalize uncertainty, reduce stakes
- **[VALUE_TEST]**: "Why does this matter to you?"
- **[SCOPE_REDUCTION]**: "If we could make one thing click in 5 minutes, what would it be?"

## Database Schema

### UserProfile
- Persistent profile across sessions
- Stores curiosity type, entry mode, uncertainty tolerance, motivation, pacing, RIASEC, communication style
- Includes total_sessions and total_topics_explored

### ConversationSession
- Individual conversation tracking
- Stores full schema_state as JSON snapshot
- Tracks turns_elapsed, topics_mentioned, final_topic

### Signal
- Individual signals extracted during conversation
- Evidence quotes, interpretations, confidence scores
- Links to specific profile fields being updated

## Development Notes

### Adding New Research Concepts

1. Add definition to `prompts/background_resources.txt`:
   ```
   [NEW_CONCEPT]: Your definition here...
   ```

2. Reference in prompts using `[NEW_CONCEPT]`

3. Auto-injection happens via `BackgroundResources.inject()`

### Adding New Branch Conditions

1. Create new prompt file: `prompts/interviewer/your_condition.txt`
2. Add to valid conditions in `ranker._classify_branch_condition()`
3. Update `generate_next_question.txt` decision logic

### Extending Schema

1. Update Pydantic models in `src/schema/full_schema.py`
2. Update SQLAlchemy models in `src/database/models.py`
3. Update ranker prompts to track new dimensions

## Testing

```bash
# Test resource injection
python -c "from src.background_resources import BackgroundResources; \
           r = BackgroundResources(); \
           print(r.get_definition('FRICTION_PROBE'))"

# Test database
python -c "from src.database.manager import DatabaseManager; \
           db = DatabaseManager(); \
           user = db.get_or_create_user('test-user'); \
           print(user)"

# Run full system with debug
python -m src.cli --debug
```

## Troubleshooting

**Database locked error**: Close other connections or delete `data/liminal.db` and restart

**JSON parsing errors**: Check ranker prompts are requesting valid JSON format

**Missing concepts**: Verify `[CONCEPT_NAME]` exists in `background_resources.txt`

**Import errors**: Run `pip install -r requirements.txt`

## Future Enhancements

- Web interface integration (use existing FastAPI backend)
- Audio support (TTS/STT already implemented in web version)
- Advanced analytics dashboard from database
- Multi-user comparison and clustering
- Adaptive prompt selection based on user success rates
- Integration with actual teaching phase (currently just transitions)

## Credits

Research foundations from:
- Litman (2005) - I-type vs D-type curiosity
- Loewenstein (1994) - Information gap theory
- Vygotsky (1978) - Zone of Proximal Development
- Hidi & Renninger (2006) - Four-phase interest development
- D'Mello et al. (2014) - Productive vs hopeless confusion
- Deci & Ryan (2000) - Self-determination theory
- Wigfield & Eccles (2000) - Expectancy-value theory
