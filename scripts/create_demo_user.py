#!/usr/bin/env python3
"""
Create a realistic demo user with learning trajectory data.
Includes plateaus, setbacks, and authentic progression.

Usage:
    python scripts/create_demo_user.py
"""

import json
import sys
import random
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.manager import DatabaseManager

# Demo user credentials
DEMO_USERNAME = "demo_learner_alex"


def create_demo_user(db: DatabaseManager):
    """Create demo user with rich trajectory data"""

    print(f"Creating demo user: {DEMO_USERNAME}")
    print("=" * 60)

    # 1. Create user profile
    print("\n[1/4] Creating user profile...")

    # Check if user already exists
    from src.database.models import UserProfile
    session = db._get_session()
    try:
        existing_user = session.query(UserProfile).filter_by(username=DEMO_USERNAME).first()
        if existing_user:
            print(f"   ! User {DEMO_USERNAME} already exists, deleting old data...")
            # Delete old data
            from src.database.models import UserGoal, ConversationSession, TrajectoryCheckpoint, LearnerTrajectory

            # Delete checkpoints
            session.query(TrajectoryCheckpoint).filter_by(user_id=existing_user.user_id).delete()
            # Delete sessions
            session.query(ConversationSession).filter_by(user_id=existing_user.user_id).delete()
            # Delete trajectory
            session.query(LearnerTrajectory).filter_by(user_id=existing_user.user_id).delete()
            # Delete goals
            session.query(UserGoal).filter_by(user_id=existing_user.user_id).delete()
            # Delete user
            session.query(UserProfile).filter_by(user_id=existing_user.user_id).delete()
            session.commit()
            print(f"   ✓ Deleted old user data")
    finally:
        session.close()

    user = db.create_user_with_username(
        username=DEMO_USERNAME,
        onboarding_info="Software engineer with 5 years experience, curious about AI alignment. Interests: machine learning interpretability, cognitive science, educational technology"
    )
    user_id = user.user_id
    print(f"   ✓ Created profile for {DEMO_USERNAME} (ID: {user_id})")

    # Update profile data manually since there's no direct method
    from src.database.models import UserProfile
    session = db._get_session()
    try:
        profile = session.query(UserProfile).filter_by(user_id=user_id).first()
        if profile:
            profile.curiosity_type = {"value": "interest", "confidence": 0.85, "evidence": []}
            profile.entry_mode = {"people": 0.2, "problems": 0.5, "ideas": 0.3}
            profile.uncertainty_tolerance = {"value": "high", "confidence": 0.75, "evidence": []}
            profile.pacing_preference = {"value": "exploratory", "confidence": 0.8}
            profile.motivation_profile = {
                "intrinsic_value": 0.9,
                "utility_value": 0.6,
                "identity_value": 0.7,
                "perceived_cost": 0.3
            }
            session.commit()
            print(f"   ✓ Updated profile attributes")
    finally:
        session.close()

    # 2. Create three goals at different stages
    print("\n[2/4] Creating learning goals...")
    goals_data = [
        {
            "goal_text": "Understand transformer architecture and attention mechanisms",
            "teaching_candidate": {"topic": "Transformers", "readiness": 0.9}
        },
        {
            "goal_text": "Learn mechanistic interpretability techniques",
            "teaching_candidate": {"topic": "Interpretability", "readiness": 0.7}
        },
        {
            "goal_text": "Build intuition for neural network optimization",
            "teaching_candidate": {}
        }
    ]

    goal_ids = []
    for goal_data in goals_data:
        goal = db.create_goal(
            user_id=user_id,
            goal_text=goal_data["goal_text"]
        )
        goal_ids.append(goal.id)

        # Update teaching candidate if present
        if goal_data["teaching_candidate"]:
            db.update_goal_teaching_candidate(goal.id, goal_data["teaching_candidate"])

        print(f"   ✓ Goal {goal.id}: {goal_data['goal_text']}")

    # 3. Create teaching sessions with realistic progression
    print("\n[3/4] Creating teaching sessions with realistic patterns...")

    # Goal 1: Transformers - Completed teaching with plateau
    print("   → Session 1: Transformer Foundations (with plateau)")
    session1_id = "demo-session-transformers-1"
    create_teaching_session_with_plateau(
        db,
        session1_id,
        user_id,
        goal_ids[0],
        topic="Transformer Architecture Foundations",
        total_turns=35,
        plateau_turns=(15, 20)  # Plateau from turn 15-20
    )
    print(f"      ✓ Created 35 checkpoints with plateau at turns 15-20")

    # Goal 1: Transformers - Second teaching with setback
    print("   → Session 2: Attention Mechanism (with setback)")
    session2_id = "demo-session-attention-1"
    create_teaching_session_with_setback(
        db,
        session2_id,
        user_id,
        goal_ids[0],
        topic="Attention Mechanism Deep Dive",
        total_turns=28,
        setback_turn=12,  # Confidence drop at turn 12
        recovery_turn=18
    )
    print(f"      ✓ Created 28 checkpoints with setback at turn 12")

    # Goal 2: Interpretability - In progress
    print("   → Session 3: Circuits Framework (in progress)")
    session3_id = "demo-session-circuits-1"
    create_teaching_session_in_progress(
        db,
        session3_id,
        user_id,
        goal_ids[1],
        topic="Transformer Circuits Framework",
        current_turn=18,
        showing_growth=True
    )
    print(f"      ✓ Created 18 checkpoints showing steady growth")

    # 4. Generate trajectory dashboard
    print("\n[4/4] Generating trajectory dashboard...")
    try:
        from src.agents.trajectory_updater import TrajectoryUpdater
        updater = TrajectoryUpdater(db=db)
        dashboard = updater.refresh(user_id=user_id)
        print(f"   ✓ Trajectory dashboard generated")
    except Exception as e:
        print(f"   ! Warning: Could not generate dashboard: {e}")
        print(f"   ! Dashboard will be generated on first view")

    print("\n" + "=" * 60)
    print("✅ Demo user created successfully!")
    print(f"\nUsername: {DEMO_USERNAME}")
    print(f"User ID: {user_id}")
    print(f"Goals: {len(goal_ids)}")
    print(f"Sessions: 3 (2 completed, 1 in progress)")
    print(f"Total checkpoints: ~81")
    print(f"\nYou can now log in with username: {DEMO_USERNAME}")
    print("=" * 60)


def create_teaching_session_with_plateau(db, session_id, user_id, goal_id, topic, total_turns, plateau_turns):
    """Create a teaching session that shows a learning plateau"""

    # Create session
    db.create_session_with_type(
        session_id=session_id,
        user_id=user_id,
        session_type="teaching",
        goal_id=goal_id,
        teaching_candidate_id=None
    )

    # Generate checkpoints with plateau pattern
    base_time = datetime.now() - timedelta(days=14)  # 2 weeks ago

    for turn in range(1, total_turns + 1):
        # Progress pattern: growth → plateau → growth
        if turn < plateau_turns[0]:
            # Early growth phase
            foundation = min(0.15 + turn * 0.02, 0.45)
            applied = min(0.10 + turn * 0.015, 0.35)
            awareness = min(0.20 + turn * 0.025, 0.55)
        elif turn <= plateau_turns[1]:
            # Plateau phase - minimal growth
            foundation = 0.45 + (turn - plateau_turns[0]) * 0.005
            applied = 0.35 + (turn - plateau_turns[0]) * 0.003
            awareness = 0.55 + (turn - plateau_turns[0]) * 0.008
        else:
            # Recovery and growth
            progress = (turn - plateau_turns[1]) / (total_turns - plateau_turns[1])
            foundation = 0.48 + progress * 0.42
            applied = 0.38 + progress * 0.47
            awareness = 0.60 + progress * 0.35

        # Add some noise
        foundation = max(0, min(1, foundation + random.uniform(-0.02, 0.02)))
        applied = max(0, min(1, applied + random.uniform(-0.02, 0.02)))
        awareness = max(0, min(1, awareness + random.uniform(-0.02, 0.02)))

        # Detect plateau event
        events = []
        if turn == plateau_turns[0]:
            events.append({
                "type": "plateau_detected",
                "description": "Learning progress has slowed - might need different approach"
            })
        if turn == plateau_turns[1] + 2:
            events.append({
                "type": "breakthrough",
                "description": "Breakthrough! Concept suddenly clicked"
            })

        # Write checkpoint
        checkpoint_time = base_time + timedelta(minutes=turn * 15)
        db.write_trajectory_checkpoint({
            "user_id": user_id,
            "session_id": session_id,
            "session_type": "teaching",
            "goal_id": goal_id,
            "teaching_candidate_id": None,
            "turn_index": turn,
            "metrics": {
                "foundational_understanding": foundation,
                "applied_mastery": applied,
                "metacognitive_awareness": awareness,
                "teaching_steps_completed": min(turn // 5, 7),
                "teaching_steps_total": 7,
                "confidence_in_profile": 0.75,
                "confidence_in_target": 0.80
            },
            "events": events,
            "created_at": checkpoint_time
        })

    # Mark session as completed by setting ended_at
    from src.database.models import ConversationSession
    session_obj = db._get_session()
    try:
        conv = session_obj.query(ConversationSession).filter_by(session_id=session_id).first()
        if conv:
            conv.ended_at = base_time + timedelta(minutes=total_turns * 15)
            conv.turns_elapsed = total_turns
            conv.schema_state = {"status": "completed"}
            session_obj.commit()
    finally:
        session_obj.close()


def create_teaching_session_with_setback(db, session_id, user_id, goal_id, topic, total_turns, setback_turn, recovery_turn):
    """Create a teaching session with a confidence setback"""

    db.create_session_with_type(
        session_id=session_id,
        user_id=user_id,
        session_type="teaching",
        goal_id=goal_id,
        teaching_candidate_id=None
    )

    base_time = datetime.now() - timedelta(days=7)

    for turn in range(1, total_turns + 1):
        if turn < setback_turn:
            # Steady growth
            foundation = 0.30 + turn * 0.03
            applied = 0.25 + turn * 0.025
            awareness = 0.35 + turn * 0.035
        elif turn <= recovery_turn:
            # Setback and confusion
            confusion_factor = 1 - (turn - setback_turn) / (recovery_turn - setback_turn)
            foundation = 0.65 - confusion_factor * 0.15
            applied = 0.55 - confusion_factor * 0.20
            awareness = 0.75 - confusion_factor * 0.10
        else:
            # Recovery with strong growth
            recovery_progress = (turn - recovery_turn) / (total_turns - recovery_turn)
            foundation = 0.65 + recovery_progress * 0.30
            applied = 0.55 + recovery_progress * 0.38
            awareness = 0.75 + recovery_progress * 0.22

        # Add noise
        foundation = max(0, min(1, foundation + random.uniform(-0.03, 0.03)))
        applied = max(0, min(1, applied + random.uniform(-0.03, 0.03)))
        awareness = max(0, min(1, awareness + random.uniform(-0.02, 0.02)))

        events = []
        if turn == setback_turn:
            events.append({
                "type": "confusion",
                "description": "Encountered difficult concept, questioning understanding"
            })
        if turn == recovery_turn:
            events.append({
                "type": "clarity",
                "description": "Misconception resolved through careful explanation"
            })

        checkpoint_time = base_time + timedelta(minutes=turn * 12)
        db.write_trajectory_checkpoint({
            "user_id": user_id,
            "session_id": session_id,
            "session_type": "teaching",
            "goal_id": goal_id,
            "teaching_candidate_id": None,
            "turn_index": turn,
            "metrics": {
                "foundational_understanding": foundation,
                "applied_mastery": applied,
                "metacognitive_awareness": awareness,
                "teaching_steps_completed": min(turn // 4, 6),
                "teaching_steps_total": 6,
                "confidence_in_profile": 0.80,
                "confidence_in_target": 0.70 if turn <= recovery_turn else 0.85
            },
            "events": events,
            "created_at": checkpoint_time
        })

    # Mark session as completed by setting ended_at
    from src.database.models import ConversationSession
    session_obj = db._get_session()
    try:
        conv = session_obj.query(ConversationSession).filter_by(session_id=session_id).first()
        if conv:
            conv.ended_at = base_time + timedelta(minutes=total_turns * 12)
            conv.turns_elapsed = total_turns
            conv.schema_state = {"status": "completed"}
            session_obj.commit()
    finally:
        session_obj.close()


def create_teaching_session_in_progress(db, session_id, user_id, goal_id, topic, current_turn, showing_growth):
    """Create an in-progress teaching session"""

    db.create_session_with_type(
        session_id=session_id,
        user_id=user_id,
        session_type="teaching",
        goal_id=goal_id,
        teaching_candidate_id=None
    )

    base_time = datetime.now() - timedelta(days=2)

    for turn in range(1, current_turn + 1):
        if showing_growth:
            # Steady upward trend
            foundation = 0.20 + turn * 0.025
            applied = 0.15 + turn * 0.020
            awareness = 0.30 + turn * 0.022
        else:
            # Slower growth
            foundation = 0.20 + turn * 0.015
            applied = 0.15 + turn * 0.012
            awareness = 0.30 + turn * 0.018

        foundation = max(0, min(1, foundation + random.uniform(-0.02, 0.02)))
        applied = max(0, min(1, applied + random.uniform(-0.02, 0.02)))
        awareness = max(0, min(1, awareness + random.uniform(-0.02, 0.02)))

        checkpoint_time = base_time + timedelta(minutes=turn * 10)
        db.write_trajectory_checkpoint({
            "user_id": user_id,
            "session_id": session_id,
            "session_type": "teaching",
            "goal_id": goal_id,
            "teaching_candidate_id": None,
            "turn_index": turn,
            "metrics": {
                "foundational_understanding": foundation,
                "applied_mastery": applied,
                "metacognitive_awareness": awareness,
                "teaching_steps_completed": min(turn // 3, 8),
                "teaching_steps_total": 8,
                "confidence_in_profile": 0.70,
                "confidence_in_target": 0.65
            },
            "events": [],
            "created_at": checkpoint_time
        })

    # Don't mark as completed - it's in progress


if __name__ == "__main__":
    db = DatabaseManager()
    create_demo_user(db)
