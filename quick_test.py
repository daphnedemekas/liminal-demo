#!/usr/bin/env python3
"""Quick test to verify concrete topic extraction."""

from src.agents.orchestrator import DiscoveryOrchestrator

orchestrator = DiscoveryOrchestrator()

# Start
opening = orchestrator.start()
print(f"Assistant: {opening}\n")

# Turn 1: Mention concrete topic
print("="*60)
print("USER: I've been curious about neural networks.")
print("="*60)
response = orchestrator.process_user_message("I've been curious about neural networks.")
print(f"Assistant: {response}\n")

schema = orchestrator.get_schema()
print(f"\n[THEMES]: {len(schema['conversational_themes'])} themes")
for t in schema['conversational_themes']:
    print(f"  - {t['theme_seed']} ({t['theme_type']})")

print(f"\n[TEACHING]: {len(schema['teaching_candidates'])} candidates")
for c in schema['teaching_candidates']:
    print(f"  - {c['topic']}")

# Turn 2: Specific gap
print("\n" + "="*60)
print("USER: I get the forward pass, but backpropagation doesn't make sense.")
print("="*60)
response = orchestrator.process_user_message("I get the forward pass, but backpropagation doesn't make sense. How does the error propagate backward?")
print(f"Assistant: {response}\n")

schema = orchestrator.get_schema()
print(f"\n[THEMES]: {len(schema['conversational_themes'])} themes")
for t in schema['conversational_themes']:
    print(f"  - {t['theme_seed']} ({t['theme_type']})")

print(f"\n[TEACHING]: {len(schema['teaching_candidates'])} candidates")
for c in schema['teaching_candidates']:
    print(f"  - {c['topic']}: {c.get('focus_question', 'no question')}")

print("\n" + "="*60)
print("EXPECTED:")
print("  - Themes should include 'neural networks' and 'backpropagation' as concrete_topic")
print("  - Teaching candidates should include 'how backpropagation propagates errors'")
