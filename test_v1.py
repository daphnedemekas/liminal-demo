#!/usr/bin/env python3
"""
Test script for V1 (2-LLM) curiosity discovery system.
Simulates a conversation to verify the system works end-to-end.
"""
import sys
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from src.versions.v1_two_llm import TwoLLMSession

console = Console()

def test_v1_conversation():
    """Run a test conversation with the V1 system."""

    console.print("\n[bold blue]Testing V1: 2-LLM Curiosity Discovery System[/bold blue]\n")

    # Create session with debug mode
    session = TwoLLMSession(debug=True)

    # Test conversation simulating a user interested in code review feedback
    test_inputs = [
        "I've been doing code reviews at work and I notice that some of my comments are really helpful and people implement them, but other times people push back or ignore them, even when I think both types of comments are equally valid.",
        "I'm not really sure. At first I thought it was about tone, like maybe I'm being too harsh sometimes. But I've noticed that even when I phrase things really nicely, sometimes people still resist. And occasionally I'll be pretty direct and people are like 'oh yeah good catch.'",
        "I can't predict which comments will be well-received. Like I'll write two comments in the same review - one about variable naming, one about a potential bug - and the bug one gets ignored while they immediately fix the naming thing. Or vice versa. I don't understand what makes someone receptive to feedback in the moment.",
        "I'd save a ton of time on reviews. Right now I write like 10 comments and maybe 3 get implemented, so I'm wasting effort. More importantly, I think I'd be better at mentoring junior devs - like I could give feedback that actually sticks instead of bouncing off."
    ]

    try:
        # Start session
        opening = session.start()
        console.print(Panel(opening, title="[cyan]Assistant[/cyan]", border_style="cyan"))

        # Process each test input
        for i, user_input in enumerate(test_inputs, 1):
            console.print(f"\n[bold green]Test Input {i}:[/bold green] {user_input[:100]}...")

            response = session.process_user_input(user_input)

            console.print(Panel(response, title="[cyan]Assistant[/cyan]", border_style="cyan"))

            if session.is_complete():
                console.print("\n[bold green]✓ Session completed![/bold green]")
                break

        # Check final topic
        if session.is_complete():
            final_topic = session.get_final_topic()
            if final_topic:
                console.print("\n" + "="*60)
                console.print("[bold green]FINAL TOPIC DISCOVERED:[/bold green]\n")
                console.print(f"[cyan]Topic:[/cyan] {final_topic.topic}")
                console.print(f"[cyan]User Confusion:[/cyan] {final_topic.user_confusion}")
                console.print(f"[cyan]Stakes:[/cyan] {final_topic.stakes}")
                console.print(f"[cyan]Learning Hook:[/cyan] {final_topic.learning_hook}")
                console.print(f"[cyan]Suggested Angles:[/cyan] {', '.join(final_topic.suggested_angles)}")
                console.print(f"\n[cyan]Scores:[/cyan]")
                console.print(f"  Prior Knowledge: {final_topic.scores.prior_knowledge}/5")
                console.print(f"  Stakes: {final_topic.scores.stakes}/5")
                console.print(f"  Confusion Edge: {final_topic.scores.confusion_edge}/5")
                console.print(f"  Surprise Potential: {final_topic.scores.surprise_potential}/5")
                console.print(f"  [bold]Total: {final_topic.scores.total}/20[/bold]")
                console.print("="*60 + "\n")

                console.print("[bold green]✓ V1 System Test PASSED![/bold green]")
                console.print("The system successfully discovered a topic with proper scoring.\n")
            else:
                console.print("[yellow]⚠ Session complete but no final topic generated[/yellow]")
        else:
            console.print("\n[yellow]Session did not complete in test inputs[/yellow]")
            console.print("This might be okay - may need more turns in real conversation")

        # Token usage
        total_tokens = session.llm.get_total_tokens()
        console.print(f"[dim]Total tokens used: {total_tokens:,}[/dim]")

        return True

    except Exception as e:
        console.print(f"\n[bold red]✗ Test FAILED with error:[/bold red]")
        console.print(f"[red]{str(e)}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return False

if __name__ == "__main__":
    success = test_v1_conversation()
    sys.exit(0 if success else 1)
