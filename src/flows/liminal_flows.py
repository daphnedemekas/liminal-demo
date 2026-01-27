"""Liminal-specific flow definitions for discovery and teaching."""
from src.flows.flow import FlowDef, FlowStep


def discovery_flow() -> FlowDef:
    """
    Discovery flow: Goal discovery → Teaching discovery.
    
    This flow represents the discovery conversation phase where the system:
    1. Discovers the user's learning goal (Phase 1)
    2. Discovers teaching targets for that goal (Phase 2)
    3. Proposes curriculum
    """
    return FlowDef(
        name="discovery",
        steps=[
            FlowStep(step="goal_discovery"),  # Phase 1: Find learning goal
            FlowStep(step="teaching_discovery"),  # Phase 2: Find teaching targets
            FlowStep(step="propose_curriculum"),  # Propose learning path
        ]
    )


def teaching_flow() -> FlowDef:
    """
    Teaching flow: Assessment → Curriculum Proposal → Teaching.
    
    This flow represents the teaching phase where the system:
    1. Assesses user's prior knowledge
    2. Proposes curriculum
    3. Negotiates curriculum (optional)
    4. Teaches the curriculum
    """
    return FlowDef(
        name="teaching",
        steps=[
            FlowStep(step="assess_knowledge"),  # Assess prior knowledge
            FlowStep(step="propose_curriculum"),  # Propose curriculum
            FlowStep(step="negotiate_curriculum"),  # Optional negotiation
            FlowStep(step="teach_curriculum"),  # Execute teaching
        ]
    )


def adaptive_flow() -> FlowDef:
    """
    Adaptive flow: LLM decides next mode.
    
    This flow uses a Choose step to let the LLM decide what to do next
    based on the current state of the conversation.
    """
    from src.flows.flow import Choose
    
    return FlowDef(
        name="adaptive",
        steps=[
            FlowStep(
                choose=Choose(
                    options={
                        "continue_discovery": [
                            {"step": "goal_discovery"},
                            {"step": "teaching_discovery"},
                        ],
                        "propose_curriculum": [
                            {"step": "propose_curriculum"},
                        ],
                        "start_teaching": [
                            {"step": "assess_knowledge"},
                            {"step": "teach_curriculum"},
                        ],
                    },
                    prompt="Based on the current conversation state, choose the next action: continue_discovery, propose_curriculum, or start_teaching"
                )
            ),
        ]
    )


def parallel_ranker_flow() -> FlowDef:
    """
    Parallel ranker flow: Execute multiple ranker updates in parallel.
    
    This flow uses fork/join to run multiple schema updates concurrently,
    then merges the results.
    """
    from src.flows.flow import Join, JoinConfig
    
    return FlowDef(
        name="parallel_ranker",
        steps=[
            FlowStep(
                fork=[
                    FlowStep(step="update_user_profile"),
                    FlowStep(step="update_conversational_themes"),
                    FlowStep(step="update_goal_candidates"),
                ]
            ),
            FlowStep(
                join=Join(join=JoinConfig(step="merge_ranker_results"))
            ),
        ]
    )




