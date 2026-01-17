#!/usr/bin/env python3
"""Test script to verify parallelization and JSON parsing fixes."""

from src.agents.orchestrator import DiscoveryOrchestrator

def main():
    print("="*60)
    print("Testing Parallelization & JSON Parsing Fixes")
    print("="*60)

    # Create orchestrator
    orchestrator = DiscoveryOrchestrator()

    # Start conversation
    print("\n[Opening Question]")
    opening = orchestrator.start()
    print(f"Assistant: {opening}\n")

    # Test turn 1: Answer with a preference signal
    print("="*60)
    print("TURN 1: Testing parallelization with preference signal")
    print("="*60)
    user_msg_1 = "It feels more like an itch - when I don't understand something, it bothers me until I figure it out."
    print(f"User: {user_msg_1}\n")

    response_1 = orchestrator.process_user_message(user_msg_1)
    print(f"Assistant: {response_1}\n")

    # Test turn 2: Mention a topic to trigger topic candidates update (the JSON parsing fix)
    print("="*60)
    print("TURN 2: Testing JSON parsing with topic mention")
    print("="*60)
    user_msg_2 = "I've been confused about how neural networks actually learn - like, I get the basic idea of layers and weights, but the backpropagation part just doesn't click."
    print(f"User: {user_msg_2}\n")

    response_2 = orchestrator.process_user_message(user_msg_2)
    print(f"Assistant: {response_2}\n")

    print("="*60)
    print("Test completed successfully!")
    print("="*60)
    print("\nCheck the timing output above:")
    print("  - Parallel analysis should show ~2-4 seconds (3 calls in parallel)")
    print("  - Controller generation should show ~1-2 seconds")
    print("  - Teaching readiness should show ~1-2 seconds")
    print("  - Total should be significantly less than the old sequential approach")
    print("\nIf no JSON errors appeared, the parsing fix is working!")

if __name__ == "__main__":
    main()
