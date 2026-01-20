"""
Understanding marker aggregation functions.

Reduces 18 individual understanding markers into 3 high-level metrics
that resonate with how learners actually feel about their progress.
"""

from typing import Dict, List


def compute_foundational_understanding(markers: Dict[str, any]) -> float:
    """
    Aggregate: Recall + Explanation + Application + Analysis
    Question: "Do I understand the basics?"

    Returns: 0.0-1.0 score
    """
    marker_ids = ["recall", "explanation", "application", "analysis"]
    return _average_marker_levels(markers, marker_ids)


def compute_applied_mastery(markers: Dict[str, any]) -> float:
    """
    Aggregate: Transfer + Connection Making + Problem Decomposition + Teaching Ability + Intuitive Grasp
    Question: "Can I actually use this in practice?"

    Returns: 0.0-1.0 score
    """
    marker_ids = ["transfer", "connection_making", "problem_decomposition", "teaching_ability", "intuitive_grasp"]
    return _average_marker_levels(markers, marker_ids)


def compute_metacognitive_awareness(markers: Dict[str, any]) -> float:
    """
    Aggregate: Metacognitive Awareness + Confidence Calibration + Error Detection + Limitation Awareness
    Question: "Do I know what I know?"

    Returns: 0.0-1.0 score
    """
    marker_ids = ["metacognitive_awareness", "confidence_calibration", "error_detection", "limitation_awareness"]
    return _average_marker_levels(markers, marker_ids)


def _average_marker_levels(markers: Dict[str, any], marker_ids: List[str]) -> float:
    """
    Convert marker levels to numeric scores and average.

    Level mapping:
    - not_yet: 0.0
    - developing: 0.5
    - strong: 1.0
    """
    level_scores = {"not_yet": 0.0, "developing": 0.5, "strong": 1.0}

    scores = []
    for marker_id in marker_ids:
        if marker_id in markers:
            marker = markers[marker_id]
            # Handle both UnderstandingMarker objects and dicts
            if hasattr(marker, 'level'):
                level = marker.level
            elif isinstance(marker, dict):
                level = marker.get('level', 'not_yet')
            else:
                continue

            scores.append(level_scores.get(level, 0.0))

    return sum(scores) / len(scores) if scores else 0.0


def compute_all_aggregates(markers: Dict[str, any]) -> Dict[str, float]:
    """
    Compute all three aggregate metrics at once.

    Args:
        markers: Dict of marker_id -> UnderstandingMarker object or dict

    Returns:
        Dict with keys: foundational_understanding, applied_mastery, metacognitive_awareness
    """
    return {
        "foundational_understanding": compute_foundational_understanding(markers),
        "applied_mastery": compute_applied_mastery(markers),
        "metacognitive_awareness": compute_metacognitive_awareness(markers)
    }
