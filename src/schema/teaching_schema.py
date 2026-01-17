"""Pydantic models for Teaching (Curriculum) phase schema."""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from enum import Enum


# ============================================================================
# Enums for Teaching Phase
# ============================================================================

class UnderstandingLevel(str, Enum):
    """Level of understanding for a marker."""
    NOT_YET = "not_yet"
    DEVELOPING = "developing"
    STRONG = "strong"


class CurriculumStepStatus(str, Enum):
    """Status of a curriculum step."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class TeachingAction(str, Enum):
    """Possible teaching actions for the controller."""
    EXPLAIN = "explain"  # Provide explanation/information
    ASK_SELF_EXPLANATION = "ask_self_explanation"  # Have user explain in their words
    COUNTERFACTUAL_PROBE = "counterfactual_probe"  # "What if X were different?"
    ERROR_DETECTION = "error_detection"  # Present common misconception to identify
    TRANSFER_PROMPT = "transfer_prompt"  # Apply to new context
    CALIBRATION_CHECK = "calibration_check"  # Check confidence vs actual understanding
    ADJUST_PLAN = "adjust_plan"  # Modify curriculum based on feedback
    ANSWER_QUESTION = "answer_question"  # Respond to user's question
    PROVIDE_EXAMPLE = "provide_example"  # Give concrete example
    CHECK_PREREQUISITE = "check_prerequisite"  # Verify needed foundation
    SUMMARIZE_PROGRESS = "summarize_progress"  # Review what's been learned


# ============================================================================
# Understanding Markers
# ============================================================================

class UnderstandingMarker(BaseModel):
    """
    Individual understanding marker tracking.
    
    These markers are based on learning science research and track
    different dimensions of understanding:
    - Cognitive (recall, explanation, application)
    - Metacognitive (self-awareness, calibration)
    - Transfer (generalization, analogy)
    """
    id: str  # e.g., "recall", "explanation", "transfer"
    name: str  # Human-readable name
    description: str  # What this marker measures
    level: UnderstandingLevel = UnderstandingLevel.NOT_YET
    evidence: List[str] = Field(default_factory=list)  # Quotes/examples demonstrating level
    notes: str = ""  # Additional observations
    last_assessed_turn: int = 0


def get_default_markers() -> List[UnderstandingMarker]:
    """Return the default set of 18 understanding markers."""
    markers = [
        # Cognitive Markers (basic understanding)
        UnderstandingMarker(
            id="recall",
            name="Recall",
            description="Can reproduce key facts, terms, and procedures"
        ),
        UnderstandingMarker(
            id="explanation",
            name="Explanation",
            description="Can explain concepts in own words"
        ),
        UnderstandingMarker(
            id="application",
            name="Application",
            description="Can use knowledge in familiar situations"
        ),
        UnderstandingMarker(
            id="analysis",
            name="Analysis",
            description="Can break down and examine relationships between parts"
        ),
        
        # Transfer Markers (deeper understanding)
        UnderstandingMarker(
            id="transfer",
            name="Transfer",
            description="Can apply concepts to novel domains or contexts"
        ),
        UnderstandingMarker(
            id="analogy_generation",
            name="Analogy Generation",
            description="Can create relevant analogies to explain concepts"
        ),
        UnderstandingMarker(
            id="connection_making",
            name="Connection Making",
            description="Links new knowledge to prior knowledge effectively"
        ),
        UnderstandingMarker(
            id="problem_decomposition",
            name="Problem Decomposition",
            description="Can break complex problems into manageable parts"
        ),
        
        # Metacognitive Markers (self-awareness)
        UnderstandingMarker(
            id="self_explanation",
            name="Self-Explanation",
            description="Can articulate their thinking process"
        ),
        UnderstandingMarker(
            id="error_detection",
            name="Error Detection",
            description="Can identify mistakes in reasoning (own or others')"
        ),
        UnderstandingMarker(
            id="metacognitive_awareness",
            name="Metacognitive Awareness",
            description="Knows what they know and don't know"
        ),
        UnderstandingMarker(
            id="confidence_calibration",
            name="Confidence Calibration",
            description="Confidence level matches actual understanding"
        ),
        UnderstandingMarker(
            id="limitation_awareness",
            name="Limitation Awareness",
            description="Knows boundaries and edge cases of applicability"
        ),
        
        # Reasoning Markers (higher-order thinking)
        UnderstandingMarker(
            id="prediction",
            name="Prediction",
            description="Can anticipate outcomes based on understanding"
        ),
        UnderstandingMarker(
            id="counterfactual_reasoning",
            name="Counterfactual Reasoning",
            description="Can reason about alternatives and 'what if' scenarios"
        ),
        UnderstandingMarker(
            id="question_generation",
            name="Question Generation",
            description="Asks meaningful, probing questions"
        ),
        
        # Communication Markers (demonstrating mastery)
        UnderstandingMarker(
            id="teaching_ability",
            name="Teaching Ability",
            description="Can explain concepts clearly to others"
        ),
        UnderstandingMarker(
            id="intuitive_grasp",
            name="Intuitive Grasp",
            description="Has gut-level, automatic understanding"
        ),
    ]
    return markers


# ============================================================================
# Curriculum Structure
# ============================================================================

class CurriculumStep(BaseModel):
    """Individual step in the curriculum plan."""
    id: int
    objective: str  # What this step teaches
    explanation_approach: str  # How to explain it (analogy, example, mechanism, etc.)
    quick_check: str  # Question to verify understanding
    marker_targets: List[str] = Field(default_factory=list)  # Which markers this step targets
    prerequisites: List[int] = Field(default_factory=list)  # IDs of prerequisite steps
    status: CurriculumStepStatus = CurriculumStepStatus.NOT_STARTED
    turns_spent: int = 0
    notes: str = ""


class CurriculumPlan(BaseModel):
    """Complete curriculum plan for a teaching topic."""
    topic: str  # The teaching candidate topic
    goal_text: str  # The broader learning goal this serves
    total_steps: int = 0
    steps: List[CurriculumStep] = Field(default_factory=list)
    current_step_id: Optional[int] = None
    completed_step_ids: List[int] = Field(default_factory=list)
    created_at_turn: int = 0
    last_modified_turn: int = 0
    
    # Adaptation tracking
    adaptations_made: int = 0  # How many times plan was modified
    adaptation_history: List[str] = Field(default_factory=list)  # Brief notes on changes


# ============================================================================
# Teaching Controller
# ============================================================================

class TeachingController(BaseModel):
    """Controller state for next teaching action."""
    next_action: TeachingAction = TeachingAction.EXPLAIN
    action_rationale: str = ""  # Why this action was chosen
    focus_content: str = ""  # What specifically to address
    target_markers: List[str] = Field(default_factory=list)  # Markers this action targets
    user_question_pending: bool = False  # User asked something that needs answering
    user_question: Optional[str] = None  # The question to answer
    
    # Adaptation signals
    confusion_detected: bool = False
    prerequisite_gap_detected: bool = False
    pacing_adjustment: Optional[Literal["slow_down", "speed_up", "maintain"]] = None


# ============================================================================
# Teaching Candidate Info (from discovery)
# ============================================================================

class TeachingCandidateInfo(BaseModel):
    """Information about the teaching candidate (from discovery phase)."""
    id: int
    topic: str
    focus_question: str
    identified_gap: str
    current_model_summary: Optional[str] = None
    stakes_summary: Optional[str] = None
    pedagogical_scope: str = "10min"  # "5min", "10min", "15min"
    angle: str = "mechanism"  # mechanism, meaning, application, historical, geometric, intuitive


# ============================================================================
# Complete Teaching Schema
# ============================================================================

class TeachingSchema(BaseModel):
    """Complete schema for Teaching (Curriculum) phase."""
    session_id: str
    user_id: str
    goal_id: int
    teaching_candidate_id: int
    
    # Core teaching content
    teaching_candidate: TeachingCandidateInfo
    curriculum_plan: CurriculumPlan = Field(default_factory=lambda: CurriculumPlan(topic="", goal_text=""))
    
    # Progress tracking
    turns_elapsed: int = 0
    current_step_index: int = 0
    
    # Understanding assessment
    understanding_markers: List[UnderstandingMarker] = Field(default_factory=get_default_markers)
    
    # Narrative summaries
    narrative_summary: str = ""  # LLM-generated summary of current understanding
    next_best_move: str = ""  # What the tutor should do next
    
    # Open issues
    open_questions: List[str] = Field(default_factory=list)  # Questions to resolve
    prerequisite_gaps: List[str] = Field(default_factory=list)  # Missing foundation
    
    # Controller
    controller: TeachingController = Field(default_factory=TeachingController)
    
    # Metadata
    phase_complete: bool = False  # Has user demonstrated sufficient understanding?
    
    class Config:
        """Pydantic config."""
        use_enum_values = True


