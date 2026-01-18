"""
Populate database with Lily Rose demo user for video recording.

Usage:
    python scripts/populate_demo_user.py

This will:
1. Create the Lily_Rose user profile
2. Create 4 learning goals across different domains
3. Create exploration session with conversation history
4. Create goal sessions with conversations
5. Create teaching candidates with source materials
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import json
import uuid

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database.models import (
    Base, UserProfile, ConversationSession, UserGoal, 
    FeedItem, LearnerTrajectory
)


def get_db_session(db_path: str = "data/liminal.db"):
    """Get a database session."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f'sqlite:///{db_path}', echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return SessionLocal()


def create_lily_rose_user(session) -> UserProfile:
    """Create or update the Lily_Rose user profile."""
    
    # Check if user already exists
    existing = session.query(UserProfile).filter_by(username="Lily_Rose").first()
    if existing:
        print(f"User Lily_Rose already exists with ID: {existing.user_id}")
        # Delete existing to recreate cleanly
        session.query(ConversationSession).filter_by(user_id=existing.user_id).delete()
        session.query(UserGoal).filter_by(user_id=existing.user_id).delete()
        session.query(FeedItem).filter_by(user_id=existing.user_id).delete()
        session.query(LearnerTrajectory).filter_by(user_id=existing.user_id).delete()
        session.delete(existing)
        session.commit()
        print("Deleted existing Lily_Rose data for clean recreation")
    
    user_id = str(uuid.uuid4())
    
    user = UserProfile(
        user_id=user_id,
        username="Lily_Rose",
        onboarding_info="""I'm an ML engineer at a research lab working on large language models. Outside of work, I'm learning jazz piano and have gotten really into sourdough baking lately. I'm particularly curious about AI interpretability - understanding what's actually happening inside the models I work with. I prefer deep dives where I can really understand the mechanisms behind things rather than surface-level overviews.""",
        
        # Learner profile data (pre-populated for demo)
        curiosity_type={
            "value": "intrinsic",
            "confidence": 0.85,
            "evidence": [
                "Expressed genuine fascination with understanding model internals beyond work requirements",
                "Curious about connections between jazz and neural networks",
                "Asks 'why' questions rather than just 'how'"
            ]
        },
        entry_mode={
            "people": 0.2,
            "problems": 0.5,
            "ideas": 0.8
        },
        uncertainty_tolerance={
            "value": "high",
            "confidence": 0.75,
            "evidence": [
                "Comfortable exploring open-ended questions",
                "Interested in emerging fields without clear answers"
            ]
        },
        interest_phase_default={
            "value": "maintained",
            "confidence": 0.7,
            "notes": "Sustains curiosity through deep exploration"
        },
        motivation_profile={
            "intrinsic_value": 0.85,
            "utility_value": 0.6,
            "identity_value": 0.7,
            "perceived_cost": 0.3
        },
        pacing_preference={
            "value": "deep_dive",
            "confidence": 0.8
        },
        riasec_hint={
            "I": 0.9,  # Investigative - high
            "A": 0.6,  # Artistic - moderate (jazz)
            "S": 0.3,  # Social - low
            "R": 0.4,  # Realistic - moderate
            "E": 0.2,  # Enterprising - low
            "C": 0.5   # Conventional - moderate
        },
        communication_style={
            "verbosity": "medium",
            "complexity": "high",
            "emotional_expression": "moderate",
            "question_asking_frequency": "high"
        },
        total_sessions=8,
        total_topics_explored=4
    )
    
    session.add(user)
    session.commit()
    session.refresh(user)
    
    print(f"Created user Lily_Rose with ID: {user_id}")
    return user


def create_goals(session, user_id: str) -> list:
    """Create the 4 learning goals."""
    
    goals_data = [
        {
            "goal_text": "Understand mechanistic interpretability in neural networks",
            "created_at": datetime.utcnow() - timedelta(days=7),
            "teaching_candidate": {
                "id": 1,
                "topic": "How attention heads encode linguistic features",
                "focus_question": "What specific patterns do individual attention heads learn to detect, and how can we identify them?",
                "identified_gap": "Understands transformer architecture conceptually but hasn't traced specific features through the network or used interpretability tools",
                "current_model_summary": "Knows attention mechanisms compute weighted combinations of values, but unclear on what specific 'features' individual heads learn",
                "stakes_summary": "Directly relevant to her work debugging LLMs - understanding what heads do helps explain model behavior",
                "readiness_score": 0.85,
                "pedagogical_scope": "15min",
                "angle": "mechanism",
                "source_material": """ATTENTION MECHANISM FUNDAMENTALS:

In transformer models, attention heads learn to detect specific patterns in text. Research has identified several categories:

1. **Positional Attention Heads**: Some heads primarily attend based on position (previous token, next token, beginning of sentence)

2. **Syntactic Heads**: Certain heads track grammatical structure:
   - Subject-verb agreement heads
   - Dependency parsing heads that connect related words
   
3. **Induction Heads**: A crucial discovery - these heads implement a simple but powerful algorithm:
   - Head A copies information from previous tokens
   - Head B looks for places where the current token appeared before
   - Together they predict "what comes after this token based on what came after it before"

4. **Feature Detection Heads**: Some heads activate on semantic features:
   - Named entity heads (detect names, places, organizations)
   - Sentiment heads (positive/negative words)
   - Topic heads (cluster related concepts)

KEY INTERPRETABILITY TECHNIQUE - ACTIVATION PATCHING:
To identify what a head does:
1. Run the model on two inputs that should differ in one specific way
2. Take the activation from Head X on input A
3. Patch it into the same position for input B
4. See how the output changes

If the output changes significantly, that head is involved in the computation you're testing.

From Anthropic's Transformer Circuits research: "We can think of attention heads as implementing 'circuits' - small algorithms that compose to produce complex behavior."
""",
                "source_citations": ["Anthropic Transformer Circuits Thread", "Elhage et al. 2021 - Mathematical Framework for Transformer Circuits", "Olsson et al. 2022 - In-context Learning and Induction Heads"]
            },
            "has_teaching_candidate": 1
        },
        {
            "goal_text": "Learn jazz chord voicings for piano",
            "created_at": datetime.utcnow() - timedelta(days=5),
            "teaching_candidate": {
                "id": 2,
                "topic": "Voice leading principles in ii-V-I progressions",
                "focus_question": "Why do certain voicings sound smoother than others, and how do you choose which notes to emphasize?",
                "identified_gap": "Can play basic jazz chords but voicings sound 'blocky' - doesn't understand why pros' voicings flow better",
                "current_model_summary": "Knows chord symbols and can play root position chords, but lacks understanding of voice leading and smooth transitions",
                "stakes_summary": "Wants to accompany herself while singing standards - smooth voicings make a huge difference in the feel",
                "readiness_score": 0.75,
                "pedagogical_scope": "10min",
                "angle": "mechanism",
                "source_material": """VOICE LEADING IN JAZZ PIANO:

The ii-V-I progression is the most common in jazz. In C major: Dm7 - G7 - Cmaj7

**Why Voice Leading Matters:**
Voice leading is about how individual notes (voices) move from one chord to the next. Good voice leading:
- Keeps common tones stationary
- Moves other voices by small intervals (steps, not leaps)
- Creates smooth, connected sound rather than "jumping" between chords

**The Problem with Root Position:**
Playing Dm7 (D-F-A-C) then G7 (G-B-D-F) in root position requires all voices to jump around. This sounds choppy.

**Shell Voicings - The Foundation:**
Use only the most essential notes: 3rd and 7th
- Dm7: F and C (3rd and 7th)
- G7: B and F (3rd and 7th)  
- Cmaj7: E and B (3rd and 7th)

Notice: The 7th of one chord becomes the 3rd of the next! This creates smooth motion.

**Left Hand Voicings:**
Play shell voicings in left hand, root omitted (bass player handles it)
- Start with 3rd on bottom: Dm7 = F-C | G7 = F-B | Cmaj7 = E-B
- Or 7th on bottom: Dm7 = C-F | G7 = B-F | Cmaj7 = B-E

**Adding Color:**
Once shells are automatic, add 9ths, 13ths:
- Dm9 = F-C-E (add the 9th)
- G13 = F-B-E (add the 13th - which is the same note!)

The 9th of ii becomes the 13th of V - another common tone connection.
""",
                "source_citations": ["Mark Levine - The Jazz Piano Book", "Barry Harris Workshop Notes"]
            },
            "has_teaching_candidate": 1
        },
        {
            "goal_text": "Understand the neuroscience of learning",
            "created_at": datetime.utcnow() - timedelta(days=2),
            "teaching_candidate": {
                "id": 3,
                "topic": "How spaced repetition affects memory consolidation",
                "focus_question": "What happens in the brain during spaced practice that makes memories stick better than massed practice?",
                "identified_gap": "Uses Anki but doesn't know why spacing works - wants to understand the mechanism to optimize her learning",
                "current_model_summary": "Knows spaced repetition 'works' empirically but can't explain the neural mechanisms",
                "stakes_summary": "As an ML engineer learning multiple complex topics, wants to learn how to learn more efficiently",
                "readiness_score": 0.7,
                "pedagogical_scope": "10min",
                "angle": "mechanism",
                "source_material": """SPACED REPETITION AND MEMORY CONSOLIDATION:

**Why Spacing Works - The Neural Story:**

1. **Synaptic Consolidation (hours)**
When you first learn something, it creates temporary synaptic connections. These need to be "consolidated" - strengthened through protein synthesis.

Key finding: This consolidation process takes time. Reviewing too soon doesn't trigger new consolidation.

2. **Systems Consolidation (days-weeks)**  
Over time, memories transfer from hippocampus (temporary storage) to neocortex (long-term storage). This happens during sleep.

Spacing allows multiple consolidation cycles to occur.

3. **The Testing Effect**
Retrieving a memory strengthens it more than re-reading. Each retrieval creates new retrieval routes.

Neural basis: Retrieval activates the same neural patterns as original encoding, plus additional prefrontal areas involved in search/selection.

4. **Desirable Difficulty**
Some forgetting between sessions is actually beneficial - it makes the retrieval harder, which strengthens the memory more.

Bjork's research: "Conditions that make learning harder in the short term often enhance long-term retention."

**Optimal Spacing Schedule:**
- First review: 1 day after learning
- Second review: 3-4 days later  
- Third review: 1-2 weeks later
- Subsequent: Increasingly longer intervals

This maps to how consolidation works - give enough time for each consolidation cycle to complete before the next retrieval.

**The Forgetting Curve Connection:**
Ebbinghaus showed memory decays exponentially without review. Each spaced retrieval "resets" and flattens the curve, making subsequent forgetting slower.
""",
                "source_citations": ["Bjork & Bjork 2011 - Desirable Difficulties", "Karpicke 2012 - Retrieval-Based Learning", "Kandel - In Search of Memory"]
            },
            "has_teaching_candidate": 1
        },
        {
            "goal_text": "Master sourdough fermentation science",
            "created_at": datetime.utcnow(),
            "teaching_candidate": {
                "id": 4,
                "topic": "How temperature affects yeast vs lactobacillus activity",
                "focus_question": "Why does the same starter produce such different results at different temperatures, and how do you use this to control flavor?",
                "identified_gap": "Follows recipes but doesn't understand why temperature matters so much - loaves are inconsistent",
                "current_model_summary": "Knows 'warmer = faster rise' but doesn't understand the yeast/bacteria balance or how it affects flavor",
                "stakes_summary": "Wants consistent, flavorful loaves - understanding the science would let her troubleshoot and experiment",
                "readiness_score": 0.65,
                "pedagogical_scope": "10min",
                "angle": "mechanism",
                "source_material": """SOURDOUGH FERMENTATION: TEMPERATURE AND MICROBIAL BALANCE

**The Two Main Players:**

1. **Wild Yeast (Saccharomyces cerevisiae and others)**
   - Primary job: Produce CO2 for rise
   - Optimal temperature: 75-82°F (24-28°C)
   - Dormant below 50°F (10°C)
   - Die above 140°F (60°C)

2. **Lactic Acid Bacteria (Lactobacillus, primarily)**
   - Primary job: Produce lactic and acetic acid (flavor!)
   - Optimal temperature: 85-95°F (29-35°C)
   - Still active at cooler temps where yeast slows down

**The Key Insight:**
Bacteria and yeast have different optimal temperatures. This lets you control the balance!

**Temperature Effects:**

*Cold (38-50°F / 3-10°C) - Retarding:*
- Yeast nearly dormant
- Bacteria slow but still working
- Result: Minimal rise, developing tangy flavor
- Use: Fridge retard for flavor development

*Cool (65-70°F / 18-21°C):*
- Yeast slow but active  
- Bacteria moderately active
- Result: Slow rise, balanced mild tang
- Use: Long room-temp ferments, milder flavor

*Warm (75-82°F / 24-28°C):*
- Yeast at optimal activity
- Bacteria very active
- Result: Good rise, developing tang
- Use: Standard bulk fermentation

*Hot (85-95°F / 29-35°C):*
- Yeast active but stressed
- Bacteria at peak - produce more acetic acid
- Result: Fast rise, very sour (vinegary)
- Use: If you want sharp sourness

**Acetic vs Lactic Acid:**
- Lactic acid: Smooth, yogurt-like tang
- Acetic acid: Sharp, vinegar-like sourness

Higher temps + oxygen favor acetic acid production.
Lower hydration also favors acetic acid.
""",
                "source_citations": ["Modernist Bread - Nathan Myhrvold", "The Sourdough School - Vanessa Kimbell", "Bread Science - Emily Buehler"]
            },
            "has_teaching_candidate": 1
        }
    ]
    
    created_goals = []
    for goal_data in goals_data:
        goal = UserGoal(
            user_id=user_id,
            goal_text=goal_data["goal_text"],
            created_at=goal_data["created_at"],
            status="active",
            teaching_candidate=goal_data["teaching_candidate"],
            has_teaching_candidate=goal_data["has_teaching_candidate"]
        )
        session.add(goal)
        session.flush()  # Get the ID
        created_goals.append(goal)
        print(f"Created goal {goal.id}: {goal_data['goal_text'][:50]}...")
    
    session.commit()
    return created_goals


def create_exploration_session(session, user_id: str) -> ConversationSession:
    """Create the exploration session with conversation history."""
    
    session_id = str(uuid.uuid4())
    
    conversation = [
        {
            "role": "assistant",
            "content": "What draws you to understanding what's happening inside the models you work with? Is it more about improving their reliability, or a deeper curiosity about how they process language?"
        },
        {
            "role": "user", 
            "content": "Honestly, both. At work I need to debug issues and explain model behavior to stakeholders. But personally, I find it fascinating - these models seem to 'understand' language in some sense, and I want to know what that actually means mechanistically."
        },
        {
            "role": "assistant",
            "content": "That's a rich intersection of practical need and genuine curiosity. The mechanistic interpretability field has been making exciting progress on exactly this question - researchers at Anthropic and elsewhere are literally tracing what individual neurons and attention heads do.\n\nYou mentioned you also play jazz piano - do you find any parallels between understanding musical structure and understanding model internals?"
        },
        {
            "role": "user",
            "content": "Actually yes! In jazz, you learn that certain chord voicings work because of voice leading principles - there are underlying rules that explain why things sound good. I wonder if there are similar hidden structures in how transformers process language."
        },
        {
            "role": "assistant", 
            "content": "That's a beautiful analogy. Voice leading creates smooth transitions by keeping common tones and moving others by small steps - it's almost like a local optimization for 'smoothness.'\n\nIn transformers, attention heads do something conceptually similar - they learn to route information efficiently. Some heads specialize in tracking syntax, others in semantic similarity. There's emerging evidence of 'circuits' - small algorithms that compose together.\n\nWhat aspect feels most compelling right now - the interpretability side, or deepening your understanding of voice leading?"
        },
        {
            "role": "user",
            "content": "The interpretability side is more urgent for work, but I'm also genuinely curious. I've been reading some papers but I don't have a clear mental model of what attention heads actually learn to detect."
        },
        {
            "role": "assistant",
            "content": "That's a great place to dive deeper. The breakthrough insight from recent interpretability work is that attention heads aren't mysterious black boxes - many of them learn recognizable patterns:\n\n- Some track syntactic relationships (subject-verb, modifier-noun)\n- Some copy information from earlier in context ('induction heads')\n- Some detect semantic features (names, sentiment, topics)\n\nWould you want to explore how to actually identify what a specific head does? There's a technique called activation patching that's particularly illuminating - it's like doing a controlled experiment on the model's internals."
        },
        {
            "role": "user",
            "content": "Yes! That sounds exactly like what I need. I want to understand the techniques, not just read about results."
        }
    ]
    
    # Create a realistic schema state for exploration
    # NOTE: Values must match Pydantic enum types in src/schema/full_schema.py
    schema_state = {
        "session_id": session_id,
        "interview_state": {
            "turns_elapsed": 4,
            "topics_mentioned": 3,
            "confidence_in_profile": 0.75,
            "confidence_in_target": 0.6,
            "goal_identified": False,
            "goal_provided": False,
            "user_goal": None,
            "frameworks_offered": 1,
            "proposed_goal": None,
            "proposed_teaching_id": None,
            "teaching_candidate_identified": False
        },
        "user_profile": {
            "entry_mode": {"people": 0.2, "problems": 0.5, "ideas": 0.8},
            "curiosity_type": {"value": "interest", "confidence": 0.85, "evidence": []},  # Valid enum: interest/deprivation/mixed
            "pacing_preference": {"value": "exploratory", "confidence": 0.8},  # Valid enum: fast_resolution/exploratory/mixed
            "uncertainty_tolerance": {"value": "high", "confidence": 0.75, "evidence": []},
            "interest_phase_default": {"value": "maintained", "confidence": 0.7, "notes": ""},
            "motivation_profile": {
                "intrinsic_value": 0.85,
                "utility_value": 0.6,
                "identity_value": 0.7,
                "perceived_cost": 0.3
            }
        },
        "conversational_themes": [
            {
                "id": 1,
                "theme_seed": "mechanistic interpretability",
                "theme_type": "concrete_topic",
                "disambiguated_hook": "mechanism",
                "readiness_score": 0.8
            },
            {
                "id": 2,
                "theme_seed": "jazz voice leading",
                "theme_type": "concrete_topic",
                "disambiguated_hook": "beauty",
                "readiness_score": 0.6
            },
            {
                "id": 3,
                "theme_seed": "how learning works",
                "theme_type": "abstract_goal",
                "readiness_score": 0.4
            }
        ],
        "teaching_candidates": [],
        "emerging_goals": [
            {
                "goal_text": "Understand mechanistic interpretability in neural networks",
                "relevance_score": 0.85,
                "evidence": ["Expressed work relevance", "Asked about specific techniques"]
            }
        ],
        "controller": {
            "next_action": "continue_probing",
            "question_intent": "explore_interest",
            "target_ambiguity": "T1_hook",  # Valid: U0_topic, U1_hook, T1_hook, etc.
            "conversation_mode": "grounded_offer",  # Valid: calibration, grounded_offer, hypothesis_correct, direct_probe
            "focus_instruction": "Continue exploring mechanistic interpretability interest"
        },
        "teaching_recommendation": {
            "ready": False,
            "reason": "Still exploring interests",
            "recommended_candidate_id": None
        }
    }
    
    exploration = ConversationSession(
        session_id=session_id,
        user_id=user_id,
        session_type='exploration',
        conversation_history=conversation,
        schema_state=schema_state,
        turns_elapsed=4,
        profile_summary="Lily is an ML engineer driven by deep mechanistic curiosity. She prefers understanding 'why' over just 'how', seeks connections across domains (linking jazz voice leading to attention mechanisms), and favors extended deep dives over quick overviews. High intrinsic motivation with practical work applications."
    )
    
    session.add(exploration)
    session.commit()
    session.refresh(exploration)
    
    print(f"Created exploration session: {session_id[:8]}...")
    return exploration


def create_goal_sessions(session, user_id: str, goals: list):
    """Create goal sessions with conversation history."""
    
    # Goal 1: Interpretability - more developed conversation
    goal1_session_id = str(uuid.uuid4())
    goal1_conversation = [
        {
            "role": "assistant",
            "content": "Let's explore mechanistic interpretability together. Before we dive into techniques, I'm curious - when you're debugging model behavior at work, what's your current approach? What tools or methods do you use?"
        },
        {
            "role": "user",
            "content": "Mostly probing classifiers and looking at attention visualizations. But the attention viz often doesn't tell me much - it shows where the model 'looked' but not what it actually computed. I've heard about activation patching but haven't tried it."
        },
        {
            "role": "assistant",
            "content": "That's a common frustration - attention weights show information flow but not computation. You've actually hit on the key distinction in interpretability:\n\n- **Attention weights** = where information comes from\n- **What's computed** = how that information gets transformed\n\nActivation patching bridges this gap by letting you test causal hypotheses. You basically ask: 'If I change this specific internal state, how does the output change?'\n\nWhat kinds of model behaviors do you most often need to debug? That might help identify where interpretability techniques would be most useful."
        },
        {
            "role": "user",
            "content": "A lot of it is understanding why the model makes certain errors - like when it gets a fact wrong that it should 'know', or when it follows instructions inconsistently. I want to understand if it's retrieving wrong information or computing something wrong."
        },
        {
            "role": "assistant",
            "content": "Perfect example. Those are exactly the kinds of questions mechanistic interpretability is starting to answer.\n\nFor factual errors, researchers have found specific 'memory heads' that retrieve information, and separate 'reasoning heads' that combine information. An error might happen at either stage.\n\nFor instruction following, there's emerging work on how models represent and track task instructions - certain heads seem to encode 'what I'm supposed to be doing right now.'\n\nI think we've identified a great first teaching target: **How attention heads encode linguistic features** - specifically, how to identify what individual heads have learned to detect. This is the foundation for diagnosing where computations go wrong.\n\nDoes that feel like the right starting point?"
        },
        {
            "role": "user",
            "content": "Yes, that's exactly what I want to understand. Let's do it."
        }
    ]
    
    goal1_schema = {
        "session_id": goal1_session_id,
        "interview_state": {
            "turns_elapsed": 3,
            "topics_mentioned": 2,
            "confidence_in_profile": 0.8,
            "confidence_in_target": 0.75,
            "goal_identified": True,
            "goal_provided": False,
            "user_goal": "Understand mechanistic interpretability in neural networks",
            "frameworks_offered": 1,
            "proposed_goal": None,
            "proposed_teaching_id": 1,
            "teaching_candidate_identified": True
        },
        "user_profile": {
            "entry_mode": {"people": 0.2, "problems": 0.5, "ideas": 0.8},
            "curiosity_type": {"value": "interest", "confidence": 0.85, "evidence": []},
            "pacing_preference": {"value": "exploratory", "confidence": 0.8},
            "uncertainty_tolerance": {"value": "high", "confidence": 0.75, "evidence": []}
        },
        "conversational_themes": [],
        "teaching_candidates": [
            {
                "id": 1,
                "topic": "How attention heads encode linguistic features",
                "focus_question": "What specific patterns do individual attention heads learn to detect?",
                "identified_gap": "Understands transformers architecturally but hasn't traced specific features",
                "disambiguated_hook": "mechanism",
                "readiness_score": 0.85
            }
        ],
        "emerging_goals": [],
        "controller": {
            "next_action": "propose_teaching",
            "question_intent": "teaching_ready",
            "target_ambiguity": "T3_gap",
            "conversation_mode": "grounded_offer",
            "focus_instruction": "Teaching candidate identified - ready to begin"
        },
        "teaching_recommendation": {
            "ready": True,
            "reason": "Teaching candidate confirmed",
            "recommended_candidate_id": 1
        }
    }
    
    goal1_session = ConversationSession(
        session_id=goal1_session_id,
        user_id=user_id,
        session_type='goal',
        goal_id=goals[0].id,
        conversation_history=goal1_conversation,
        schema_state=goal1_schema,
        turns_elapsed=3,
        profile_summary="Working on interpretability for practical debugging needs. Has used basic tools but wants deeper mechanistic understanding."
    )
    session.add(goal1_session)
    
    # Goal 2: Jazz - briefer conversation
    goal2_session_id = str(uuid.uuid4())
    goal2_conversation = [
        {
            "role": "assistant",
            "content": "Tell me about your current level with jazz piano - are you working through a method book, jamming with recordings, or taking lessons?"
        },
        {
            "role": "user",
            "content": "Self-taught mostly. I can play chord symbols from lead sheets, but my voicings sound really basic compared to players I admire. Everything sounds 'blocky' instead of flowing."
        },
        {
            "role": "assistant",
            "content": "That 'blocky' feeling is the classic sign of playing root-position chords without voice leading. It's like the difference between jumping from one position to another versus walking smoothly.\n\nThe key insight in jazz piano is: the 3rd and 7th of each chord are the most important notes, and they often move by small intervals to the next chord. That creates the smooth 'flow' you're hearing in better players.\n\nHave you worked with ii-V-I progressions much? They're the building block of jazz and perfect for learning voice leading."
        },
        {
            "role": "user",
            "content": "I know ii-V-I is everywhere but I just play the chords as I see them. What should I be doing differently?"
        }
    ]
    
    goal2_schema = {
        "session_id": goal2_session_id,
        "interview_state": {
            "turns_elapsed": 2,
            "topics_mentioned": 1,
            "confidence_in_profile": 0.75,
            "confidence_in_target": 0.65,
            "goal_identified": True,
            "goal_provided": False,
            "user_goal": "Learn jazz chord voicings for piano",
            "frameworks_offered": 0,
            "proposed_goal": None,
            "proposed_teaching_id": 2,
            "teaching_candidate_identified": True
        },
        "user_profile": {
            "entry_mode": {"people": 0.2, "problems": 0.5, "ideas": 0.8},
            "curiosity_type": {"value": "interest", "confidence": 0.85, "evidence": []},
            "pacing_preference": {"value": "exploratory", "confidence": 0.8},
            "uncertainty_tolerance": {"value": "high", "confidence": 0.75, "evidence": []}
        },
        "conversational_themes": [],
        "teaching_candidates": [{
            "id": 2,
            "topic": "Voice leading principles in ii-V-I progressions",
            "focus_question": "Why do certain voicings sound smoother than others?",
            "identified_gap": "Can play basic chords but lacks voice leading understanding",
            "disambiguated_hook": "mechanism",
            "readiness_score": 0.75
        }],
        "emerging_goals": [],
        "controller": {
            "next_action": "propose_teaching",
            "question_intent": "teaching_ready",
            "target_ambiguity": "T3_gap",
            "conversation_mode": "grounded_offer",
            "focus_instruction": "Teaching candidate identified"
        },
        "teaching_recommendation": {
            "ready": True,
            "reason": "Teaching candidate confirmed",
            "recommended_candidate_id": 2
        }
    }
    
    goal2_session = ConversationSession(
        session_id=goal2_session_id,
        user_id=user_id,
        session_type='goal',
        goal_id=goals[1].id,
        conversation_history=goal2_conversation,
        schema_state=goal2_schema,
        turns_elapsed=2
    )
    session.add(goal2_session)
    
    # Goal 3 and 4: Minimal conversations (newer goals)
    for i, goal in enumerate(goals[2:], start=3):
        sess_id = str(uuid.uuid4())
        minimal_schema = {
            "session_id": sess_id,
            "interview_state": {
                "turns_elapsed": 0,
                "topics_mentioned": 0,
                "confidence_in_profile": 0.7,
                "confidence_in_target": 0.3,
                "goal_identified": True,
                "goal_provided": False,
                "user_goal": goal.goal_text,
                "frameworks_offered": 0,
                "proposed_goal": None,
                "proposed_teaching_id": None,
                "teaching_candidate_identified": False
            },
            "user_profile": {
                "entry_mode": {"people": 0.2, "problems": 0.5, "ideas": 0.8},
                "curiosity_type": {"value": "interest", "confidence": 0.85, "evidence": []},
                "pacing_preference": {"value": "exploratory", "confidence": 0.8},
                "uncertainty_tolerance": {"value": "high", "confidence": 0.75, "evidence": []}
            },
            "conversational_themes": [],
            "teaching_candidates": [],
            "emerging_goals": [],
            "controller": {
                "next_action": "continue_probing",
                "question_intent": "explore_interest",
                "target_ambiguity": "T1_hook",
                "conversation_mode": "calibration",
                "focus_instruction": "Explore user's background in this goal"
            },
            "teaching_recommendation": {
                "ready": False,
                "reason": "Still discovering teaching candidate",
                "recommended_candidate_id": None
            }
        }
        sess = ConversationSession(
            session_id=sess_id,
            user_id=user_id,
            session_type='goal',
            goal_id=goal.id,
            conversation_history=[{
                "role": "assistant",
                "content": f"Let's explore {goal.goal_text.lower()} together. What drew you to this topic?"
            }],
            schema_state=minimal_schema,
            turns_elapsed=0
        )
        session.add(sess)
    
    session.commit()
    print(f"Created {len(goals)} goal sessions")


def create_teaching_session(session, user_id: str, goal_id: int, teaching_candidate_id: int):
    """Create a teaching session for the first goal (interpretability)."""
    
    session_id = str(uuid.uuid4())
    
    conversation = [
        {
            "role": "assistant",
            "content": """Great! Let's explore **How attention heads encode linguistic features** together.

Based on our conversation, here's what I'm thinking for our learning path:

1. **Understand the chain rule foundation - why attention heads need to specialize**
2. **See how researchers identify what individual heads do**
3. **Learn the activation patching technique**
4. **Practice interpreting head behavior on a real example**
5. **Connect to debugging workflows**

We'll start with the fundamentals and build up from there. The goal is for you to really understand this - not just know the facts, but be able to reason about it and apply it.

What specific patterns do individual attention heads learn to detect, and how can we identify them?

What's your current mental model of what a single attention head actually computes? Even a rough intuition helps me understand where to start."""
        },
        {
            "role": "user",
            "content": "I know each head computes attention weights - where to 'look' - and then takes a weighted sum of values. But I don't have a clear picture of why that would lead to detecting specific patterns. Like, why would one head end up detecting syntax while another detects something else?"
        },
        {
            "role": "assistant",
            "content": """That's actually a great foundation. Let me build on it.\n\nThe key insight is that attention heads learn through **gradient descent** - they adjust their weights to minimize loss. But here's what makes it interesting: each head has limited capacity, so heads end up **specializing** in different tasks.\n\nThink of it like a team where everyone is trying to be useful:\n- If Head A gets really good at tracking syntax, it reduces the error\n- Now Head B doesn't need to duplicate that work - it can specialize in something else that still has errors\n- This creates a natural **division of labor**\n\nThe query and key matrices essentially define what each head is \"looking for\" and what counts as a match. A syntax head might learn queries that encode \"I'm a verb, looking for my subject\" and keys that encode \"I'm a noun that could be a subject.\"\n\nDoes this help explain why specialization emerges? What feels clear vs. fuzzy here?"""
        }
    ]
    
    schema_state = {
        "session_id": session_id,
        "user_id": user_id,
        "goal_id": goal_id,
        "teaching_candidate_id": teaching_candidate_id,
        "turns_elapsed": 1,
        "current_step_index": 0,
        "phase_complete": False,
        "teaching_candidate": {
            "id": teaching_candidate_id,
            "topic": "How attention heads encode linguistic features",
            "focus_question": "What specific patterns do individual attention heads learn to detect?",
            "identified_gap": "Understands transformers architecturally but hasn't traced specific features"
        },
        "curriculum_plan": {
            "topic": "How attention heads encode linguistic features",
            "goal_text": "Understand mechanistic interpretability in neural networks",
            "total_steps": 5,
            "steps": [
                {
                    "id": 1,
                    "objective": "Understand why attention heads specialize",
                    "explanation_approach": "Division of labor analogy + gradient descent intuition",
                    "quick_check": "Why don't all heads learn the same thing?",
                    "marker_targets": ["explanation", "intuitive_grasp"],
                    "prerequisites": [],
                    "status": "in_progress",
                    "turns_spent": 1
                },
                {
                    "id": 2,
                    "objective": "Learn what kinds of patterns heads detect",
                    "explanation_approach": "Concrete examples: positional, syntactic, induction heads",
                    "quick_check": "What's an induction head looking for?",
                    "marker_targets": ["recall", "explanation"],
                    "prerequisites": [1],
                    "status": "not_started",
                    "turns_spent": 0
                },
                {
                    "id": 3,
                    "objective": "Understand activation patching technique",
                    "explanation_approach": "Controlled experiment analogy + step-by-step procedure",
                    "quick_check": "How would you test if a head is involved in a task?",
                    "marker_targets": ["application", "explanation"],
                    "prerequisites": [2],
                    "status": "not_started",
                    "turns_spent": 0
                },
                {
                    "id": 4,
                    "objective": "Practice interpreting head behavior",
                    "explanation_approach": "Walk through a real research example together",
                    "quick_check": "What would you conclude from this patching result?",
                    "marker_targets": ["application", "analysis"],
                    "prerequisites": [3],
                    "status": "not_started",
                    "turns_spent": 0
                },
                {
                    "id": 5,
                    "objective": "Connect to debugging workflows",
                    "explanation_approach": "Practical application to her work context",
                    "quick_check": "How would you apply this to your debugging?",
                    "marker_targets": ["transfer", "application"],
                    "prerequisites": [4],
                    "status": "not_started",
                    "turns_spent": 0
                }
            ],
            "current_step_id": 1,
            "completed_step_ids": []
        },
        "understanding_markers": [
            {"id": "recall", "name": "Recall", "level": "not_assessed", "evidence": []},
            {"id": "explanation", "name": "Explanation", "level": "emerging", "evidence": ["Can articulate basic attention mechanism"]},
            {"id": "application", "name": "Application", "level": "not_assessed", "evidence": []},
            {"id": "transfer", "name": "Transfer", "level": "not_assessed", "evidence": []},
            {"id": "intuitive_grasp", "name": "Intuitive Grasp", "level": "emerging", "evidence": ["Good question about specialization"]}
        ]
    }
    
    teaching = ConversationSession(
        session_id=session_id,
        user_id=user_id,
        session_type='teaching',
        goal_id=goal_id,
        teaching_candidate_id=teaching_candidate_id,
        conversation_history=conversation,
        schema_state=schema_state,
        turns_elapsed=1,
        profile_summary="Technical ML engineer with strong foundation in attention mechanisms. Learns best through mechanistic explanations and connecting theory to practical debugging."
    )
    
    session.add(teaching)
    session.commit()
    
    print(f"Created teaching session: {session_id[:8]}...")


def create_feed_items(session, user_id: str, goals: list):
    """Create feed items for exploration and goals."""
    
    # Exploration feed items
    exploration_items = [
        {
            "title": "Circuits: Mathematical Framework for Transformer Circuits",
            "content": "This foundational work from Anthropic demonstrates that transformer attention heads can be understood as implementing interpretable algorithms. The research shows how to reverse-engineer what specific heads compute, revealing structure like 'induction heads' that implement in-context learning.",
            "source_citation": "Elhage et al., Anthropic 2021",
            "source_url": "https://transformer-circuits.pub/2021/framework/index.html",
            "relevance_note": "Directly addresses your interest in understanding what happens inside LLMs",
            # Tags
            "relevance_level": "high",
            "relevance_reason": "You mentioned wanting to understand what happens inside LLMs - this paper pioneered the field of mechanistic interpretability.",
            "difficulty_level": "intermediate",
            "difficulty_reason": "Assumes familiarity with transformer architecture and linear algebra, which aligns with your ML engineering background.",
            "content_type": "theory",
            "content_type_reason": "This is foundational theoretical work that establishes the conceptual framework for analyzing neural networks.",
            "priority_tag": "foundation",
            "priority_reason": "This is the starting point for mechanistic interpretability - other papers build on these concepts.",
            "connection_tags": [{"topic": "AI Interpretability", "reason": "Core reading for your interpretability learning goal"}]
        },
        {
            "title": "Voice Leading in Jazz Piano: A Practical Approach",
            "content": "Voice leading creates smooth transitions between chords by minimizing motion in individual voices. In jazz, this often means prioritizing the 3rd and 7th (the 'shell' voicing) which contain the chord quality and can move smoothly to the next chord.",
            "source_citation": "Mark Levine - The Jazz Piano Book",
            "relevance_note": "Connects your musical interest to the mechanistic understanding you value",
            # Tags
            "relevance_level": "high",
            "relevance_reason": "Directly relevant to your jazz piano interest - this is the core technique for smooth chord progressions.",
            "difficulty_level": "beginner",
            "difficulty_reason": "Shell voicings are accessible to piano beginners and don't require advanced theory knowledge.",
            "content_type": "technique",
            "content_type_reason": "This is a practical technique you can apply immediately at the piano.",
            "priority_tag": "foundation",
            "priority_reason": "Shell voicings are the starting point for jazz piano - master these before adding extensions.",
            "connection_tags": [{"topic": "Jazz", "reason": "Key technique for your jazz chord voicings goal"}]
        },
        {
            "title": "Desirable Difficulties in Learning",
            "content": "Research shows that conditions making learning feel harder often improve long-term retention. Spacing practice sessions, varying practice conditions, and testing yourself all introduce 'desirable difficulties' that strengthen memory.",
            "source_citation": "Bjork & Bjork, 2011",
            "relevance_note": "Understanding learning science could optimize how you acquire these new skills",
            # Tags
            "relevance_level": "medium",
            "relevance_reason": "Meta-learning insight that could improve how you approach all your learning goals.",
            "difficulty_level": "beginner",
            "difficulty_reason": "Accessible cognitive science research with practical takeaways - no prerequisites needed.",
            "content_type": "concept",
            "content_type_reason": "Introduces a key concept in learning science that changes how you think about practice.",
            "priority_tag": "optional",
            "priority_reason": "Helpful but not essential - focus on your main goals first.",
            "connection_tags": [
                {"topic": "Learning Science", "reason": "Connects to your neuroscience of learning goal"},
                {"topic": "Jazz", "reason": "Apply spacing to your piano practice"},
                {"topic": "Sourdough", "reason": "Spacing helps build procedural memory for baking"}
            ]
        }
    ]
    
    for i, item in enumerate(exploration_items):
        feed_item = FeedItem(
            user_id=user_id,
            context_type='exploration',
            title=item["title"],
            content=item["content"],
            source_citation=item.get("source_citation"),
            source_url=item.get("source_url"),
            relevance_note=item.get("relevance_note"),
            relevance_level=item.get("relevance_level"),
            relevance_reason=item.get("relevance_reason"),
            difficulty_level=item.get("difficulty_level"),
            difficulty_reason=item.get("difficulty_reason"),
            content_type=item.get("content_type"),
            content_type_reason=item.get("content_type_reason"),
            priority_tag=item.get("priority_tag"),
            priority_reason=item.get("priority_reason"),
            connection_tags=item.get("connection_tags"),
            display_order=i
        )
        session.add(feed_item)
    
    # Goal-specific feed items for each goal
    goal_feed_items = {
        0: [  # Interpretability
            {
                "title": "In-context Learning and Induction Heads",
                "content": "This paper shows that a specific circuit called 'induction heads' is responsible for in-context learning in transformers. These heads implement a simple algorithm: find where the current token appeared before, and predict what came after it.",
                "source_citation": "Olsson et al., 2022",
                "relevance_note": "Concrete example of mechanistic interpretability in action",
                "relevance_level": "high",
                "relevance_reason": "Directly addresses your goal of understanding mechanistic interpretability - this is one of the most important papers in the field.",
                "difficulty_level": "intermediate",
                "difficulty_reason": "Requires understanding of attention mechanism basics, which you have from your ML background.",
                "content_type": "example",
                "content_type_reason": "A worked example of finding and understanding a specific circuit in transformers.",
                "priority_tag": "next-step",
                "priority_reason": "After the Circuits framework, this paper shows the methodology applied to a specific phenomenon."
            },
            {
                "title": "Activation Patching Tutorial",
                "content": "Activation patching is a causal intervention technique: you run a model on two inputs, take an activation from one run, and 'patch' it into the other run to see how the output changes. This reveals which components are causally involved in a computation.",
                "source_citation": "Anthropic Tutorial",
                "relevance_note": "The technique you asked about - how to test what heads actually do",
                "relevance_level": "high",
                "relevance_reason": "This is the practical technique you'll use to actually do interpretability research.",
                "difficulty_level": "intermediate",
                "difficulty_reason": "Requires PyTorch knowledge and understanding of model internals - you have the ML background for this.",
                "content_type": "technique",
                "content_type_reason": "Hands-on methodology you can apply to any model.",
                "priority_tag": "foundation",
                "priority_reason": "Core technique - learn this before moving to more advanced analysis methods."
            }
        ],
        1: [  # Jazz chord voicings
            {
                "title": "Shell Voicings: The Foundation of Jazz Piano",
                "content": "Shell voicings use only the 3rd and 7th of each chord - the notes that define the chord quality. In a ii-V-I in C, the shells are: Dm7 (F-C), G7 (F-B), Cmaj7 (E-B). Notice how the F stays still and only one note moves each time.",
                "source_citation": "Mark Levine - The Jazz Piano Book",
                "relevance_note": "The core technique for smooth voice leading",
                "relevance_level": "high",
                "relevance_reason": "This is exactly what you need to learn jazz chord voicings - the foundational technique.",
                "difficulty_level": "beginner",
                "difficulty_reason": "Only requires knowing how to find notes on the piano - no prior jazz theory needed.",
                "content_type": "technique",
                "content_type_reason": "Practical technique you can practice immediately at the piano.",
                "priority_tag": "foundation",
                "priority_reason": "Start here - shell voicings are the base layer everything else builds on."
            },
            {
                "title": "Why Voice Leading Creates Flow",
                "content": "Voice leading minimizes the 'jumps' between chords by keeping common tones stationary and moving other notes by the smallest possible interval. This creates a sense of inevitability - each chord flows naturally into the next.",
                "source_citation": "Barry Harris Workshop",
                "relevance_note": "The underlying principle that makes jazz voicings work",
                "relevance_level": "high",
                "relevance_reason": "Understanding the 'why' behind voice leading will help you apply it intuitively.",
                "difficulty_level": "beginner",
                "difficulty_reason": "Conceptual explanation that doesn't require technical knowledge.",
                "content_type": "concept",
                "content_type_reason": "The mental model that guides how to construct voicings.",
                "priority_tag": "foundation",
                "priority_reason": "Understanding voice leading principles helps you create your own voicings, not just memorize patterns."
            }
        ],
        2: [  # Neuroscience of learning
            {
                "title": "The Testing Effect and Memory",
                "content": "Retrieving information from memory strengthens the memory more than re-reading. Each retrieval creates new neural pathways and connections. This is why flashcards and self-testing work better than passive review.",
                "source_citation": "Karpicke & Roediger, 2008",
                "relevance_note": "Why active recall beats passive review",
                "relevance_level": "high",
                "relevance_reason": "Foundational finding in learning science that applies to all your learning goals.",
                "difficulty_level": "beginner",
                "difficulty_reason": "Accessible research finding with clear practical implications.",
                "content_type": "concept",
                "content_type_reason": "Key concept that changes how you think about learning.",
                "priority_tag": "foundation",
                "priority_reason": "Core principle of effective learning - apply this to all your practice.",
                "connection_tags": [
                    {"topic": "Jazz", "reason": "Test yourself by playing voicings without looking"},
                    {"topic": "Interpretability", "reason": "Quiz yourself on circuit concepts"}
                ]
            },
            {
                "title": "Sleep and Memory Consolidation",
                "content": "During sleep, memories transfer from the hippocampus (short-term) to the neocortex (long-term). Spaced repetition works partly because it gives consolidation time to occur between sessions.",
                "source_citation": "Walker - Why We Sleep",
                "relevance_note": "The biological basis for spacing out your practice",
                "relevance_level": "medium",
                "relevance_reason": "Explains why spacing works - useful context but not essential to apply the technique.",
                "difficulty_level": "beginner",
                "difficulty_reason": "Accessible neuroscience - no prerequisites needed.",
                "content_type": "theory",
                "content_type_reason": "The biological mechanism underlying spaced repetition.",
                "priority_tag": "deep-dive",
                "priority_reason": "Nice to understand but not necessary for effective learning."
            }
        ],
        3: [  # Sourdough fermentation
            {
                "title": "The Yeast-Bacteria Balance",
                "content": "Sourdough is a symbiosis between wild yeast (for rise) and lactobacillus bacteria (for flavor). They have different optimal temperatures: yeast peaks at 75-82°F while bacteria prefer 85-95°F. This lets you control the balance.",
                "source_citation": "Modernist Bread",
                "relevance_note": "The key insight for controlling your sourdough",
                "relevance_level": "high",
                "relevance_reason": "This is the core mechanism of sourdough - understanding this lets you troubleshoot any problem.",
                "difficulty_level": "intermediate",
                "difficulty_reason": "Requires applying temperature concepts to your baking - some trial and error involved.",
                "content_type": "concept",
                "content_type_reason": "The fundamental mechanism you need to understand to control your sourdough.",
                "priority_tag": "foundation",
                "priority_reason": "Understanding this lets you diagnose why your bread is too sour, not sour enough, or not rising.",
                "connection_tags": [
                    {"topic": "Learning Science", "reason": "Like learning - conditions matter more than time"}
                ]
            },
            {
                "title": "Cold Fermentation for Flavor",
                "content": "Refrigerating dough (38-50°F) slows yeast dramatically but bacteria keep working slowly. This develops complex flavors without over-proofing. A 12-24 hour cold retard creates depth you can't get with room temperature fermentation.",
                "source_citation": "Tartine Bread",
                "relevance_note": "Why serious bakers use the fridge",
                "relevance_level": "high",
                "relevance_reason": "This technique is how you get bakery-quality flavor at home.",
                "difficulty_level": "beginner",
                "difficulty_reason": "Simple technique - just requires a fridge and time.",
                "content_type": "technique",
                "content_type_reason": "A specific method you can apply to your next bake.",
                "priority_tag": "next-step",
                "priority_reason": "Once you have a basic sourdough working, add cold fermentation to improve flavor."
            }
        ]
    }
    
    for goal_idx, items in goal_feed_items.items():
        for i, item in enumerate(items):
            feed_item = FeedItem(
                user_id=user_id,
                context_type='goal',
                goal_id=goals[goal_idx].id,
                title=item["title"],
                content=item["content"],
                source_citation=item.get("source_citation"),
                source_url=item.get("source_url"),
                relevance_note=item.get("relevance_note"),
                relevance_level=item.get("relevance_level"),
                relevance_reason=item.get("relevance_reason"),
                difficulty_level=item.get("difficulty_level"),
                difficulty_reason=item.get("difficulty_reason"),
                content_type=item.get("content_type"),
                content_type_reason=item.get("content_type_reason"),
                priority_tag=item.get("priority_tag"),
                priority_reason=item.get("priority_reason"),
                connection_tags=item.get("connection_tags"),
                display_order=i
            )
            session.add(feed_item)
    
    session.commit()
    print(f"Created feed items for exploration and all goals")


def create_trajectory(session, user_id: str, goals: list):
    """Create learner trajectory dashboard state."""
    
    trajectory = LearnerTrajectory(
        user_id=user_id,
        dashboard_state={
            "version": 1,
            "user_id": user_id,
            "updated_at": datetime.utcnow().isoformat(),
            "insights": "Lily shows strong intrinsic curiosity with a preference for understanding mechanisms. She naturally connects concepts across domains (jazz voice leading ↔ attention patterns in transformers), suggesting high transfer potential. Her exploratory pacing and high uncertainty tolerance make her well-suited for open-ended research topics.",
            "highlights": [
                {
                    "id": 1,
                    "kind": "pattern",
                    "summary": "Strong mechanistic curiosity - consistently asks 'why' questions",
                    "evidence_quote": "I want to know what that actually means mechanistically"
                },
                {
                    "id": 2,
                    "kind": "connection",
                    "summary": "Cross-domain pattern recognition (jazz ↔ ML)",
                    "evidence_quote": "there are underlying rules that explain why things sound good. I wonder if there are similar hidden structures"
                },
                {
                    "id": 3,
                    "kind": "preference",
                    "summary": "Prefers deep dives over breadth",
                    "evidence_quote": "I want to understand the techniques, not just read about results"
                }
            ],
            "goals": [
                {
                    "goal_id": goals[0].id,
                    "goal_text": "Understand mechanistic interpretability in neural networks",
                    "status": "active",
                    "momentum": "engaged",
                    "learning_summary": "Identified attention head encoding as first teaching target",
                    "next_suggested_move": "Start teaching session on activation patching"
                },
                {
                    "goal_id": goals[1].id,
                    "goal_text": "Learn jazz chord voicings for piano",
                    "status": "active",
                    "momentum": "starting",
                    "learning_summary": "Identified voice leading as key gap",
                    "next_suggested_move": "Practice ii-V-I progressions with shell voicings"
                },
                {
                    "goal_id": goals[2].id,
                    "goal_text": "Understand the neuroscience of learning",
                    "status": "active",
                    "momentum": "exploring",
                    "learning_summary": None,
                    "next_suggested_move": "Explore spaced repetition mechanisms"
                },
                {
                    "goal_id": goals[3].id,
                    "goal_text": "Master sourdough fermentation science",
                    "status": "active",
                    "momentum": "exploring",
                    "learning_summary": None,
                    "next_suggested_move": "Understand temperature effects on yeast vs bacteria"
                }
            ],
            "engagement": {
                "sessions_per_week": [2, 3, 2, 4],
                "turns_per_session": [8, 12, 6, 10],
                "mode_mix": {"text": 0.8, "voice": 0.2}
            },
            "learner_model": {
                "stability": {
                    "confidence_in_profile": [0.3, 0.5, 0.65, 0.75],
                    "confidence_in_target": [0.2, 0.4, 0.5, 0.6]
                },
                "entry_mode": [{"ideas": 0.7, "problems": 0.5, "people": 0.2}],
                "pacing_preference": ["exploratory", "exploratory", "exploratory"],
                "uncertainty_tolerance": ["high", "high", "high"],
                "curiosity_type": ["interest", "interest", "interest"],
                "motivation_profile": [{
                    "intrinsic": 0.85,
                    "utility": 0.6,
                    "identity": 0.7,
                    "cost": 0.3
                }]
            }
        },
        last_checkpoint_id=None
    )
    
    session.add(trajectory)
    session.commit()
    print(f"Created learner trajectory for user")


def main():
    """Main function to populate demo user."""
    print("=" * 60)
    print("Populating Lily Rose Demo User")
    print("=" * 60)
    
    db_session = get_db_session()
    
    try:
        # Create user
        user = create_lily_rose_user(db_session)
        
        # Create goals
        goals = create_goals(db_session, user.user_id)
        
        # Create exploration session
        create_exploration_session(db_session, user.user_id)
        
        # Create goal sessions
        create_goal_sessions(db_session, user.user_id, goals)
        
        # Create teaching session for first goal
        create_teaching_session(
            db_session, 
            user.user_id, 
            goals[0].id,
            teaching_candidate_id=1
        )
        
        # Create feed items
        create_feed_items(db_session, user.user_id, goals)
        
        # Create trajectory
        create_trajectory(db_session, user.user_id, goals)
        
        print()
        print("=" * 60)
        print("SUCCESS! Demo user Lily_Rose has been created.")
        print("=" * 60)
        print()
        print("Summary:")
        print(f"  User ID: {user.user_id}")
        print(f"  Username: Lily_Rose")
        print(f"  Goals: {len(goals)}")
        print(f"    1. Understand mechanistic interpretability (with teaching session)")
        print(f"    2. Learn jazz chord voicings")
        print(f"    3. Understand neuroscience of learning")
        print(f"    4. Master sourdough fermentation")
        print()
        print("You can now log in as 'Lily_Rose' in the app!")
        
    except Exception as e:
        print(f"Error: {e}")
        db_session.rollback()
        raise
    finally:
        db_session.close()


if __name__ == "__main__":
    main()

