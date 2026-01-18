"""
Setup a fresh demo user for video recording.

This creates a minimal user with the specified background.
Conversations will be generated live by the LLM during the demo.

Usage:
    python scripts/setup_demo_fresh.py
"""

import sys
from pathlib import Path
from datetime import datetime
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


def create_demo_user(session) -> UserProfile:
    """Create the demo user with minimal setup."""
    
    # Check if user already exists
    existing = session.query(UserProfile).filter_by(username="Demo_User").first()
    if existing:
        print(f"User Demo_User already exists, deleting for clean recreation...")
        session.query(ConversationSession).filter_by(user_id=existing.user_id).delete()
        session.query(UserGoal).filter_by(user_id=existing.user_id).delete()
        session.query(FeedItem).filter_by(user_id=existing.user_id).delete()
        session.query(LearnerTrajectory).filter_by(user_id=existing.user_id).delete()
        session.delete(existing)
        session.commit()
    
    user_id = str(uuid.uuid4())
    
    # The background from the plan
    onboarding_info = """I am trying to start an AI company, I studied math and machine learning. For hobbies I like reading, pottery, painting, trying to balance my analytical and creative parts. Right now I'm quite interested in LLMs and what would be the best way to prevent hallucination and sycophancy, and how to cleanly design a loop that helps a person learn about something they are interested in through an interaction with an LLM. Wondering about prompt engineering, reinforcement learning, RAG, and how to measure and verify human comprehension. But I have a broad range of interests as well, spanning art history, music, physics, biology, the future of science."""
    
    user = UserProfile(
        user_id=user_id,
        username="Demo_User",
        onboarding_info=onboarding_info,
        
        # Minimal learner profile - will be built during conversation
        curiosity_type={"value": "interest", "confidence": 0.5, "evidence": []},
        entry_mode={"people": 0.3, "problems": 0.6, "ideas": 0.7},
        uncertainty_tolerance={"value": "high", "confidence": 0.5, "evidence": []},
        interest_phase_default={"value": "maintained", "confidence": 0.5, "notes": ""},
        motivation_profile={
            "intrinsic_value": 0.7,
            "utility_value": 0.8,
            "identity_value": 0.6,
            "perceived_cost": 0.3
        },
        pacing_preference={"value": "exploratory", "confidence": 0.5},
        riasec_hint={
            "I": 0.8,  # Investigative - high (ML/math)
            "A": 0.7,  # Artistic - high (pottery, painting)
            "S": 0.4,  # Social
            "R": 0.5,  # Realistic
            "E": 0.7,  # Enterprising (starting company)
            "C": 0.5   # Conventional
        },
        communication_style={
            "verbosity": "medium",
            "complexity": "complex",  # Valid: simple, medium, complex
            "emotional_expression": "expressive",  # Valid: reserved, neutral, expressive
            "question_asking_frequency": "high"
        },
        total_sessions=0,
        total_topics_explored=0
    )
    
    session.add(user)
    session.commit()
    session.refresh(user)
    
    print(f"Created user Demo_User with ID: {user_id}")
    return user


def main():
    """Main function to setup fresh demo user."""
    print("=" * 60)
    print("Setting up Fresh Demo User")
    print("=" * 60)
    
    db_session = get_db_session()
    
    try:
        # Create user
        user = create_demo_user(db_session)
        
        print()
        print("=" * 60)
        print("SUCCESS! Fresh demo user has been created.")
        print("=" * 60)
        print()
        print("Summary:")
        print(f"  User ID: {user.user_id}")
        print(f"  Username: Demo_User")
        print()
        print("Next steps:")
        print("  1. Start the backend: python -m uvicorn backend.main:app --reload --port 8000")
        print("  2. Start the frontend: cd frontend && npm run dev")
        print("  3. Log in as 'Demo_User' in the app")
        print("  4. The LLM will generate all conversations in real-time")
        print()
        print("Demo flow:")
        print("  - Exploration: AI will propose goals based on background")
        print("  - Goal Chat: AI will assess prior knowledge, propose learning tasks")
        print("  - Learning Task Chat: AI will assess, propose curriculum, teach")
        
    except Exception as e:
        print(f"Error: {e}")
        db_session.rollback()
        raise
    finally:
        db_session.close()


if __name__ == "__main__":
    main()

