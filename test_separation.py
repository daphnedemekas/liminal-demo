#!/usr/bin/env python3
"""Test script to verify conversational themes vs teaching candidates separation."""

from src.agents.orchestrator import DiscoveryOrchestrator
import json

def print_themes_and_candidates(schema_dict):
    """Print both conversational themes and teaching candidates."""
    print("\n" + "="*60)
    print("CONVERSATIONAL THEMES (all patterns, goals, topics):")
    print("="*60)

    themes = schema_dict.get("conversational_themes", [])
    if themes:
        for theme in themes:
            print(f"\n  Theme ID {theme.get('id')}: {theme.get('theme_seed')}")
            print(f"    Type: {theme.get('theme_type')}")
            print(f"    Specificity: {theme.get('specificity')}")
            print(f"    Probing depth: {theme.get('probing_depth')}")
    else:
        print("  (none yet)")

    print("\n" + "="*60)
    print("TEACHING CANDIDATES (concrete, teachable concepts only):")
    print("="*60)

    candidates = schema_dict.get("teaching_candidates", [])
    if candidates:
        for cand in candidates:
            print(f"\n  Candidate ID {cand.get('id')}: {cand.get('topic')}")
            print(f"    Focus question: {cand.get('focus_question')}")
            print(f"    Gap: {cand.get('identified_gap')}")
            print(f"    Concreteness test: {cand.get('book_chapter_test')}")
            print(f"    Pedagogical scope: {cand.get('pedagogical_scope')}")
            print(f"    Readiness score: {cand.get('readiness_score')}")
    else:
        print("  (none yet)")

    print("\n" + "="*60)

def main():
    print("="*60)
    print("Testing Conversational Themes vs Teaching Candidates Separation")
    print("="*60)

    # Create orchestrator
    orchestrator = DiscoveryOrchestrator()

    # Start conversation
    print("\n[Opening Question]")
    opening = orchestrator.start()
    print(f"Assistant: {opening}\n")

    # Test turn 1: Abstract goal (should be theme only, NOT teaching candidate)
    print("="*60)
    print("TURN 1: Testing abstract goal tracking")
    print("="*60)
    user_msg_1 = "It feels like an itch. When I don't understand something, I get this nagging feeling that won't go away until I figure it out."
    print(f"User: {user_msg_1}\n")

    response_1 = orchestrator.process_user_message(user_msg_1)
    print(f"Assistant: {response_1}\n")

    print_themes_and_candidates(orchestrator.get_schema())

    # Test turn 2: Broad topic (should be theme, probably not teaching candidate yet)
    print("\n" + "="*60)
    print("TURN 2: Testing broad topic mention")
    print("="*60)
    user_msg_2 = "I've been thinking about neural networks lately. The whole deep learning thing just seems like black magic to me."
    print(f"User: {user_msg_2}\n")

    response_2 = orchestrator.process_user_message(user_msg_2)
    print(f"Assistant: {response_2}\n")

    print_themes_and_candidates(orchestrator.get_schema())

    # Test turn 3: Specific gap (should create teaching candidate!)
    print("\n" + "="*60)
    print("TURN 3: Testing specific gap identification")
    print("="*60)
    user_msg_3 = "I get the forward pass - you just multiply weights and add biases. But backpropagation doesn't make sense to me. How does the error actually propagate backward?"
    print(f"User: {user_msg_3}\n")

    response_3 = orchestrator.process_user_message(user_msg_3)
    print(f"Assistant: {response_3}\n")

    print_themes_and_candidates(orchestrator.get_schema())

    # Check teaching readiness
    teaching_rec = orchestrator.get_schema().get('teaching_recommendation', {})
    print("\n" + "="*60)
    print("TEACHING READINESS:")
    print("="*60)
    print(f"Ready: {teaching_rec.get('ready')}")
    if teaching_rec.get('ready'):
        print(f"Target topic: {teaching_rec.get('target_topic')}")
        print(f"Focus question: {teaching_rec.get('focus_question')}")
        print(f"First move: {teaching_rec.get('first_move')}")

    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)
    print("\nExpected behavior:")
    print("  - Turn 1: Abstract goal in conversational_themes, NOT in teaching_candidates")
    print("  - Turn 2: Broad topic in conversational_themes, probably not yet in teaching_candidates")
    print("  - Turn 3: Should create teaching_candidate for 'how backpropagation calculates gradients'")
    print("  - Teaching recommendation should ONLY consider teaching_candidates, not themes")

if __name__ == "__main__":
    main()
