"""Pydantic models for the complete curiosity discovery schema."""
from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Literal
from enum import Enum


# ============================================================================
# Enums for constrained values
# ============================================================================

class CuriosityType(str, Enum):
    """Type of epistemic curiosity (Litman)."""
    INTEREST = "interest"  # I-type: pleasure of learning
    DEPRIVATION = "deprivation"  # D-type: itch of not knowing
    MIXED = "mixed"


class ToleranceLevel(str, Enum):
    """Tolerance for uncertainty."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class InterestPhase(str, Enum):
    """Four-phase interest development (Hidi & Renninger)."""
    TRIGGERED = "triggered"  # Triggered situational
    MAINTAINED = "maintained"  # Maintained situational
    EMERGING = "emerging"  # Emerging individual
    DEVELOPED = "developed"  # Well-developed individual


class PacingPreference(str, Enum):
    """User's preferred pacing."""
    FAST_RESOLUTION = "fast_resolution"
    EXPLORATORY = "exploratory"
    MIXED = "mixed"


class RPLFit(str, Enum):
    """Region of Proximal Learning fit."""
    TOO_EASY = "too_easy"
    PROXIMAL = "proximal"
    TOO_HARD = "too_hard"
    UNKNOWN = "unknown"


class Specificity(str, Enum):
    """Topic specificity level."""
    BROAD = "broad"
    MEDIUM = "medium"
    SPECIFIC = "specific"


class GoalType(str, Enum):
    """Type of learning goal."""
    SKILL_ACQUISITION = "skill_acquisition"
    CONCEPTUAL_UNDERSTANDING = "conceptual_understanding"
    PROJECT_COMPLETION = "project_completion"
    INTUITION_BUILDING = "intuition_building"


class ConfusionType(str, Enum):
    """Type of confusion."""
    PRODUCTIVE = "productive"
    HOPELESS = "hopeless"
    UNCLEAR = "unclear"


# ============================================================================
# User Profile Components
# ============================================================================

class CuriosityTypeField(BaseModel):
    """Curiosity type with confidence and evidence."""
    value: Optional[CuriosityType] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list)


class EntryMode(BaseModel):
    """How user frames interests (RIASEC-related)."""
    people: float = Field(default=0.0, ge=0.0, le=1.0)  # Social entry
    problems: float = Field(default=0.0, ge=0.0, le=1.0)  # Practical entry
    ideas: float = Field(default=0.0, ge=0.0, le=1.0)  # Conceptual entry


class UncertaintyTolerance(BaseModel):
    """Tolerance for ambiguity and uncertainty."""
    value: Optional[ToleranceLevel] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list)


class InterestPhaseDefault(BaseModel):
    """Default interest development phase."""
    value: Optional[InterestPhase] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: str = ""


class MotivationProfile(BaseModel):
    """Expectancy-value theory motivations."""
    intrinsic_value: float = Field(default=0.0, ge=0.0, le=1.0)
    utility_value: float = Field(default=0.0, ge=0.0, le=1.0)
    identity_value: float = Field(default=0.0, ge=0.0, le=1.0)
    perceived_cost: float = Field(default=0.0, ge=0.0, le=1.0)


class PacingPreferenceField(BaseModel):
    """User's preferred learning pace."""
    value: Optional[PacingPreference] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class RIASECHint(BaseModel):
    """RIASEC interest texture hints."""
    I: float = Field(default=0.0, ge=0.0, le=1.0)  # Investigative
    A: float = Field(default=0.0, ge=0.0, le=1.0)  # Artistic
    S: float = Field(default=0.0, ge=0.0, le=1.0)  # Social
    R: float = Field(default=0.0, ge=0.0, le=1.0)  # Realistic
    E: float = Field(default=0.0, ge=0.0, le=1.0)  # Enterprising
    C: float = Field(default=0.0, ge=0.0, le=1.0)  # Conventional


class CommunicationStyle(BaseModel):
    """User's communication patterns."""
    verbosity: Literal["brief", "medium", "verbose"] = "medium"
    complexity: Literal["simple", "medium", "complex"] = "medium"
    emotional_expression: Literal["reserved", "neutral", "expressive"] = "neutral"
    question_asking_frequency: Literal["low", "medium", "high"] = "medium"


class UserProfile(BaseModel):
    """Complete user profile tracking 20+ dimensions."""
    curiosity_type: CuriosityTypeField = Field(default_factory=CuriosityTypeField)
    entry_mode: EntryMode = Field(default_factory=EntryMode)
    uncertainty_tolerance: UncertaintyTolerance = Field(default_factory=UncertaintyTolerance)
    interest_phase_default: InterestPhaseDefault = Field(default_factory=InterestPhaseDefault)
    motivation_profile: MotivationProfile = Field(default_factory=MotivationProfile)
    pacing_preference: PacingPreferenceField = Field(default_factory=PacingPreferenceField)
    riasec_hint: RIASECHint = Field(default_factory=RIASECHint)
    communication_style: CommunicationStyle = Field(default_factory=CommunicationStyle)


# ============================================================================
# Signal Tracking
# ============================================================================

class Signal(BaseModel):
    """Individual signal extracted from conversation."""
    turn: int
    type: str  # affect, value, goal, confusion, preference, identity, etc.
    evidence_quote: str
    interpretation: str
    updates_field: str  # e.g., "user_profile.curiosity_type"
    confidence: float = Field(ge=0.0, le=1.0)


# ============================================================================
# Conversational Theme Tracking
# ============================================================================

class ConversationalTheme(BaseModel):
    """
    Conversational themes that emerge during discovery.

    These can be abstract patterns, metacognitive goals, preferences, or concrete topics.
    Examples: "wants to overcome overwhelm", "prefers visual learning", "neural networks"

    This is valuable user profiling data but not necessarily teachable content.
    """
    id: int
    theme_seed: str  # Initial mention
    theme_type: Literal["abstract_goal", "preference", "concrete_topic", "metacognitive_pattern"] = "concrete_topic"
    disambiguated_hook: Optional[str] = None  # mechanism, meaning, usefulness, beauty, weirdness
    user_phase: Optional[InterestPhase] = None
    current_model_summary: Optional[str] = None  # User's existing understanding
    identified_gap: Optional[str] = None  # Specific gap or confusion
    specificity: Specificity = Specificity.BROAD
    estimated_RPL_fit: RPLFit = RPLFit.UNKNOWN

    # Value and stakes
    intrinsic_value: float = Field(default=0.0, ge=0.0, le=1.0)
    utility_value: float = Field(default=0.0, ge=0.0, le=1.0)
    identity_value: float = Field(default=0.0, ge=0.0, le=1.0)
    perceived_cost: float = Field(default=0.0, ge=0.0, le=1.0)

    # Probing progress
    probing_depth: Literal["mentioned", "hook_identified", "model_elicited", "gap_identified", "scope_reduced"] = "mentioned"
    readiness_score: float = Field(default=0.0, ge=0.0, le=1.0)

    # Confusion tracking
    confusion_type: Optional[ConfusionType] = None
    confusion_notes: str = ""

    # Goal relevance (Phase 2 only - teaching discovery)
    goal_relevance: Optional[Literal["within_goal", "related", "tangential"]] = None

    # Metadata
    turns_discussed: int = 0
    last_mentioned_turn: int = 0


# Legacy alias for backwards compatibility
TopicCandidate = ConversationalTheme


# ============================================================================
# Teaching Candidate Tracking
# ============================================================================

class TeachingCandidate(BaseModel):
    """
    Concrete conceptual topics that can actually be taught.

    STRICT CRITERIA:
    - Must be a specific conceptual topic you could read about in a book/article
    - Must have clear pedagogical scope (can be explained in 5-15 minutes)
    - Must NOT be abstract goals, preferences, or metacognitive patterns

    Examples of VALID teaching candidates:
    - "how backpropagation calculates gradients"
    - "why TCP uses a three-way handshake"
    - "what eigenvalues represent geometrically"
    - "how CRISPR edits DNA sequences"

    Examples of INVALID (these go in conversational_themes instead):
    - "wants to feel less overwhelmed by complexity"
    - "prefers visual explanations"
    - "neural networks" (too broad - needs narrowing)
    - "struggles with abstraction"
    """
    id: int
    topic: str  # Specific conceptual topic
    source_theme_id: Optional[int] = None  # Which conversational theme spawned this

    # The specific question/gap to address
    focus_question: str  # "How does X work?", "Why does Y happen?", "What is Z?"
    identified_gap: str  # Specific confusion or missing piece

    # User's current understanding
    current_model_summary: Optional[str] = None

    # Concreteness validation
    is_concrete: bool = True  # Must pass concreteness test
    book_chapter_test: str = ""  # "Could you find a chapter about this specific thing?"
    pedagogical_scope: Literal["5min", "10min", "15min", "too_broad"] = "10min"

    # Hook and angle
    disambiguated_hook: str  # mechanism, meaning, application, beauty
    angle: Literal["mechanism", "meaning", "application", "historical", "geometric", "intuitive"] = "mechanism"

    # RPL fit
    estimated_RPL_fit: RPLFit = RPLFit.UNKNOWN
    specificity: Specificity = Specificity.MEDIUM

    # Stakes tracking (U5) - why this matters to the user
    stakes_clarified: bool = False
    stakes_summary: Optional[str] = None  # Why this matters to them (their words)
    # Note: Using str instead of Literal to be more permissive with LLM outputs
    # Valid values: "intrinsic", "utility", "identity", "urgency", or None/empty
    stakes_type: Optional[str] = None

    # Readiness (readiness_score is a convenience metric for ranking, not used for decisions)
    readiness_score: float = Field(default=0.0, ge=0.0, le=1.0)
    # NOTE: ready_to_teach removed - readiness is now calculated by code from attributes

    # Metadata
    turns_discussed: int = 0
    last_mentioned_turn: int = 0


class GoalCandidate(BaseModel):
    """
    High-level learning outcomes that require multiple lessons to accomplish.

    DISTINCTION FROM TEACHING CANDIDATES:
    - Goal candidates are multi-lesson outcomes (e.g., "Become conversational in Spanish")
    - Teaching candidates are single-lesson gaps (e.g., "How to conjugate present tense verbs")
    - Goal candidates are break-apartable into teaching candidates

    CRITERIA:
    - Outcome-oriented ("be able to X", "understand Y intuitively", "build Z")
    - Requires multiple lessons (weeks/months, not hours/years)
    - Break-apartable into 3+ distinct teachable sub-goals
    - Concrete and achievable scope

    Examples:
    - "Become conversational in Spanish"
    - "Understand quantum mechanics intuitively"
    - "Build a full-stack web application"
    - "Develop geometric intuition for linear algebra"
    """
    id: int
    goal: str  # Clear statement of learning outcome
    goal_type: GoalType = GoalType.CONCEPTUAL_UNDERSTANDING

    # Outcome and breakdown
    outcome_description: str  # What success looks like
    example_sub_goals: List[str] = Field(default_factory=list)  # 3-5 teachable sub-goals
    estimated_lessons: str = "10-20"  # "5-10", "10-20", "20-30", "30+"

    # Assessment dimensions
    concreteness: float = Field(default=0.0, ge=0.0, le=1.0)  # Is outcome clear and specific?
    break_apartability: float = Field(default=0.0, ge=0.0, le=1.0)  # Can identify distinct sub-goals?
    scope_appropriateness: float = Field(default=0.0, ge=0.0, le=1.0)  # Multi-lesson but achievable?
    user_commitment: float = Field(default=0.0, ge=0.0, le=1.0)  # Interest/motivation level?

    # Overall readiness
    readiness_score: float = Field(default=0.0, ge=0.0, le=1.0)  # Average of above 4

    # Motivation tracking
    user_motivation_summary: Optional[str] = None  # Why this matters to them
    stakes_clarified: bool = False

    # Metadata
    turns_discussed: int = 0
    last_mentioned_turn: int = 0


# ============================================================================
# Interview State
# ============================================================================

class InterviewState(BaseModel):
    """Current state of the discovery interview."""
    turns_elapsed: int = 0
    dimensions_explored: List[str] = Field(default_factory=list)
    dimensions_remaining: List[str] = Field(default_factory=lambda: [
        "curiosity_type",
        "entry_mode",
        "uncertainty_tolerance",
        "interest_phase",
        "motivation_profile",
        "pacing_preference",
        "riasec_hint"
    ])
    topics_mentioned: int = 0
    topics_fully_probed: int = 0
    confidence_in_profile: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_in_target: float = Field(default=0.0, ge=0.0, le=1.0)
    ready_for_teach_phase: bool = False
    frameworks_offered: int = 0  # Track how many cognitive frameworks we've offered (max 2)
    
    # Track recent questions to avoid repetition
    recent_question_intents: List[str] = Field(default_factory=list)  # Last 5 question intents
    recent_question_summaries: List[str] = Field(default_factory=list)  # Brief summaries of last 5 questions

    # Goal tracking
    user_goal: Optional[str] = None  # User's stated learning goal (e.g., "Learn jazz harmony")
    goal_provided: bool = False      # Did user provide a goal upfront?
    goal_identified: bool = False    # Has a learning goal been identified? (for exploratory mode)
    proposed_goal: Optional[str] = None  # Goal proposed to user but not yet confirmed
    proposed_goal_id: Optional[int] = None  # ID of the proposed goal candidate
    rejected_goal_ids: List[int] = Field(default_factory=list)  # Goal candidates user rejected
    accepted_goal_ids: List[int] = Field(default_factory=list)  # Goal candidates user already accepted (don't re-propose)
    last_goal_accepted_turn: Optional[int] = None  # Turn number when last goal was accepted (for cooldown)
    
    # Teaching candidate tracking (Phase 2)
    teaching_candidate_identified: bool = False  # Has a teaching candidate been selected?
    proposed_teaching_id: Optional[int] = None  # ID of teaching candidate proposed to user
    rejected_teaching_ids: List[int] = Field(default_factory=list)  # Teaching candidates user rejected


# ============================================================================
# Controller
# ============================================================================

class Controller(BaseModel):
    """Controller state for next action."""
    next_action: str  # general_explore, probe_topic, narrow_scope, test_value, confirm_target, etc.
    focus_instruction: str = ""  # High-level strategy/insight to guide the Interviewer (not the final question text)
    question_intent: str = ""  # understand_learning_style, disambiguate_hook, extract_gap, etc.
    fallback_questions: List[str] = Field(default_factory=list)
    branch_condition: str = "unclear"  # topic_mentioned, personal_shared, deflection, preference_signal, question_asked, unclear
    
    # Conversation mode selection for recognition-based patterns
    conversation_mode: Optional[Literal[
        "calibration",       # Early turns, forced-choice A/B questions
        "grounded_offer",    # Mid-game, offer content + reaction question
        "hypothesis_correct", # Stuck on fuzzy topic, guess + ask what's wrong
        "direct_probe"       # Standard question without grounding
    ]] = None
    
    # Ambiguity targeting for intentional progress
    target_ambiguity: Optional[Literal[
        # General/legacy targets
        "U0_topic",          # What domain/phenomenon?
        "U1_hook",           # Why do they care?
        "U2_model",          # What do they already know?
        "U3_gap",            # What specific confusion?
        "U4_scope",          # What's the right size target?
        "U5_stakes",         # Why does this matter to them?
        "profile_dimension", # Learning style/preference
        # Goal Discovery phase targets (G0-G5)
        "G0_domain",         # What broad area?
        "G1_type",           # What type of goal?
        "G2_relationship",   # How do they relate to this?
        "G3_outcome",        # What outcome do they want?
        "G4_scope",          # Is scope appropriate?
        "G5_commitment",     # Are they committed?
        # Teaching Discovery phase targets (T1-T5)
        "T1_hook",           # Why this specific topic?
        "T2_model",          # What do they already know?
        "T3_gap",            # What's the specific gap?
        "T4_scope",          # Right size for teaching?
        "T5_stakes"          # Why does this matter?
    ]] = None
    target_teaching_candidate_id: Optional[int] = None  # Which candidate is this question about?
    
    @model_validator(mode='before')
    @classmethod
    def migrate_next_question(cls, data):
        """Handle old 'next_question' field by mapping to 'focus_instruction'."""
        if isinstance(data, dict):
            # If LLM outputs old field name, migrate it
            if 'next_question' in data and 'focus_instruction' not in data:
                data['focus_instruction'] = data.pop('next_question')
        return data


# ============================================================================
# Teaching Recommendation
# ============================================================================

class TeachingRecommendation(BaseModel):
    """Recommendation for teaching phase."""
    ready: bool = False
    target_topic_id: Optional[int] = None
    target_topic: Optional[str] = None
    focus_question: Optional[str] = None  # The specific question to answer
    angle: Optional[str] = None  # mechanism, meaning, application, etc.
    difficulty_calibration: Optional[str] = None  # ZPD-appropriate difficulty
    format: Optional[str] = None  # dialogue, explanation, analogy, example
    pacing: Optional[str] = None  # fast_resolution, exploratory
    first_move: Optional[str] = None  # Opening move for teaching phase


# ============================================================================
# Complete Schema
# ============================================================================

class DiscoverySchema(BaseModel):
    """Complete schema for curiosity discovery."""
    session_id: str
    user_profile: UserProfile = Field(default_factory=UserProfile)
    signals: List[Signal] = Field(default_factory=list)

    # Conversational themes: All patterns, goals, preferences, and topics that emerge
    conversational_themes: List[ConversationalTheme] = Field(default_factory=list)

    # Goal candidates: High-level multi-lesson learning outcomes (exploratory phase 1)
    goal_candidates: List[GoalCandidate] = Field(default_factory=list)

    # Teaching candidates: ONLY concrete conceptual topics that can be taught (exploratory phase 2 / goal-directed)
    teaching_candidates: List[TeachingCandidate] = Field(default_factory=list)

    interview_state: InterviewState = Field(default_factory=InterviewState)
    controller: Controller
    teaching_recommendation: TeachingRecommendation = Field(default_factory=TeachingRecommendation)

    class Config:
        """Pydantic config."""
        use_enum_values = True
