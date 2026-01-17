#!/usr/bin/env python3
"""
Test V1 with a vague start to verify repair patterns work.
"""
import sys
from rich.console import Console
from rich.panel import Panel

from src.versions.v1_two_llm import TwoLLMSession

console = Console()

def test_v1_vague_start():
    """Test with vague initial answer."""

    console.print("\n[bold blue]Testing V1 with Vague Start (Repair Patterns)[/bold blue]\n")

    session = TwoLLMSession(debug=True)

    # Simulating a user who starts vague and needs concretizing
    test_inputs = [
        "I'm interested in AI and machine learning.",  # Vague start
        "Well, I was using ChatGPT to summarize meeting notes and it kept making up action items that weren't discussed.",  # Concrete moment
        "I think maybe it's guessing based on what usually happens in meetings? But I don't understand why it can't tell what's real versus what it's making up.",  # Beliefs + confusion
        "I'd know whether I can trust these tools for work stuff. Right now I'm afraid to use it for anything important."  # Stakes
    ]

    try:
        opening = session.start()
        console.print(Panel(opening, title="[cyan]Assistant[/cyan]", border_style="cyan"))

        for i, user_input in enumerate(test_inputs, 1):
            console.print(f"\n[bold green]User Turn {i}:[/bold green] {user_input}")

            response = session.process_user_input(user_input)
            console.print(Panel(response, title="[cyan]Assistant[/cyan]", border_style="cyan"))

            if session.is_complete():
                break

        if session.is_complete():
            topic = session.get_final_topic()
            console.print("\n[bold green]✓ Successfully guided vague start to concrete topic![/bold green]\n")
            console.print(f"Final Topic: {topic.topic}")
            console.print(f"Scores: Knowledge={topic.scores.prior_knowledge}, Stakes={topic.scores.stakes}, Confusion={topic.scores.confusion_edge}, Surprise={topic.scores.surprise_potential}")
            console.print(f"Total: {topic.scores.total}/20\n")
        else:
            console.print("\n[yellow]Session ongoing - would continue in real conversation[/yellow]\n")

        console.print(f"[dim]Tokens: {session.llm.get_total_tokens():,}[/dim]")
        return True

    except Exception as e:
        console.print(f"\n[bold red]✗ Test FAILED: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_v1_vague_start()
    sys.exit(0 if success else 1)
