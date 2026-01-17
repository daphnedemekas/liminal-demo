"""CLI interface for research-based discovery system."""
import argparse
import json
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt
from src.agents.orchestrator import DiscoveryOrchestrator


console = Console()


def print_welcome():
    """Print welcome message."""
    welcome_text = """
# Liminal Curiosity Discovery

A research-based system that helps you discover what you're genuinely curious about.

This conversation typically takes 5-8 exchanges. Just answer naturally - there are no wrong answers.

Type 'quit' or 'exit' at any time to stop.
"""
    console.print(Panel(Markdown(welcome_text), border_style="blue"))


def print_schema_debug(schema_dict: dict):
    """Print schema state for debugging."""
    console.print("\n[dim]═══════════ Schema State ═══════════[/dim]")

    # Interview state
    interview_state = schema_dict.get("interview_state", {})
    console.print(f"[dim]Turn:[/dim] {interview_state.get('turns_elapsed', 0)}")
    console.print(f"[dim]Topics Mentioned:[/dim] {interview_state.get('topics_mentioned', 0)}")
    console.print(f"[dim]Confidence in Profile:[/dim] {interview_state.get('confidence_in_profile', 0):.2f}")
    console.print(f"[dim]Confidence in Target:[/dim] {interview_state.get('confidence_in_target', 0):.2f}")

    # User profile - all dimensions
    profile = schema_dict.get("user_profile", {})
    console.print(f"\n[bold dim]User Profile:[/bold dim]")

    curiosity = profile.get('curiosity_type', {})
    console.print(f"  [dim]Curiosity Type:[/dim] {curiosity.get('value', 'unknown')} (conf: {curiosity.get('confidence', 0):.2f})")
    if curiosity.get('evidence'):
        console.print(f"    [dim]Evidence:[/dim] {curiosity['evidence'][0][:60]}..." if len(curiosity['evidence'][0]) > 60 else curiosity['evidence'][0])

    entry = profile.get('entry_mode', {})
    console.print(f"  [dim]Entry Mode:[/dim] people={entry.get('people', 0):.2f}, problems={entry.get('problems', 0):.2f}, ideas={entry.get('ideas', 0):.2f}")

    uncertainty = profile.get('uncertainty_tolerance', {})
    console.print(f"  [dim]Uncertainty Tolerance:[/dim] {uncertainty.get('value', 'unknown')} (conf: {uncertainty.get('confidence', 0):.2f})")

    motivation = profile.get('motivation_profile', {})
    console.print(f"  [dim]Motivation:[/dim] intrinsic={motivation.get('intrinsic_value', 0):.2f}, utility={motivation.get('utility_value', 0):.2f}, identity={motivation.get('identity_value', 0):.2f}")

    riasec = profile.get('riasec_hint', {})
    if any(v > 0.3 for v in riasec.values()):
        console.print(f"  [dim]RIASEC:[/dim] I={riasec.get('I', 0):.2f}, A={riasec.get('A', 0):.2f}, S={riasec.get('S', 0):.2f}")

    console.print(f"  [dim]Pacing:[/dim] {profile.get('pacing_preference', {}).get('value', 'unknown')}")

    # Signals extracted
    signals = schema_dict.get("signals", [])
    if signals:
        console.print(f"\n[bold dim]Signals Extracted ({len(signals)}):[/bold dim]")
        for sig in signals[-3:]:  # Show last 3
            console.print(f"  - Turn {sig.get('turn')}: {sig.get('type')} (conf: {sig.get('confidence', 0):.2f})")
            console.print(f"    [dim]\"{sig.get('evidence_quote', '')[:70]}...\"[/dim]")

    # Topic candidates
    topics = schema_dict.get("topic_candidates", [])
    if topics:
        console.print(f"\n[bold dim]Topic Candidates ({len(topics)}):[/bold dim]")
        for t in topics:
            console.print(f"  - {t.get('topic_seed', 'unknown')}")
            console.print(f"    [dim]Readiness:[/dim] {t.get('readiness_score', 0):.2f} | [dim]Probing:[/dim] {t.get('probing_depth', 'unknown')}")
            console.print(f"    [dim]Hook:[/dim] {t.get('disambiguated_hook', 'unknown')} | [dim]RPL Fit:[/dim] {t.get('estimated_RPL_fit', 'unknown')}")
            if t.get('identified_gap'):
                console.print(f"    [dim]Gap:[/dim] {t.get('identified_gap', '')[:80]}...")
            console.print(f"    [dim]Values:[/dim] intrinsic={t.get('intrinsic_value', 0):.2f}, utility={t.get('utility_value', 0):.2f}")

    # Controller
    controller = schema_dict.get("controller", {})
    console.print(f"\n[bold dim]Controller:[/bold dim]")
    console.print(f"  [dim]Next Action:[/dim] {controller.get('next_action', 'unknown')}")
    console.print(f"  [dim]Question Intent:[/dim] {controller.get('question_intent', 'unknown')}")
    console.print(f"  [dim]Branch Condition:[/dim] {controller.get('branch_condition', 'unknown')}")
    console.print(f"  [dim]Focus Instruction:[/dim] {controller.get('focus_instruction', 'none')[:80]}...")

    # Teaching readiness
    teaching = schema_dict.get("teaching_recommendation", {})
    if teaching.get("ready"):
        console.print(f"\n[bold green]Ready for Teaching![/bold green]")
        console.print(f"  [dim]Topic:[/dim] {teaching.get('target_topic')}")
        console.print(f"  [dim]Focus:[/dim] {teaching.get('focus_question')}")
        console.print(f"  [dim]Angle:[/dim] {teaching.get('angle')}")
        console.print(f"  [dim]First Move:[/dim] {teaching.get('first_move', '')[:80]}...")

    console.print("[dim]═══════════════════════════════════[/dim]\n")


def main():
    parser = argparse.ArgumentParser(description="Liminal Curiosity Discovery")
    parser.add_argument("--user-id", help="User ID for persistent profile")
    parser.add_argument("--debug", action="store_true", help="Show schema state after each turn")
    parser.add_argument("--verbose", action="store_true", help="Show full JSON schema (very detailed)")
    args = parser.parse_args()

    print_welcome()

    # Create orchestrator
    try:
        orchestrator = DiscoveryOrchestrator(user_id=args.user_id)
    except Exception as e:
        console.print(f"[red]Error initializing system: {e}[/red]")
        console.print("[yellow]Make sure you have set ANTHROPIC_API_KEY in your .env file[/yellow]")
        return

    # Start conversation
    opening = orchestrator.start()
    console.print(f"\n[bold cyan]Assistant:[/bold cyan] {opening}\n")

    # Conversation loop
    turn_count = 0
    max_turns = 20  # Safety limit

    while turn_count < max_turns:
        turn_count += 1

        # Get user input
        try:
            user_input = Prompt.ask("[bold green]You[/bold green]")
        except KeyboardInterrupt:
            console.print("\n[yellow]Conversation interrupted.[/yellow]")
            break

        # Check for quit
        if user_input.lower() in ['quit', 'exit', 'q']:
            console.print("\n[yellow]Ending conversation...[/yellow]")
            break

        if not user_input.strip():
            console.print("[dim]Please enter a response.[/dim]")
            continue

        # Process message with status indicator
        with console.status("[bold blue]Analyzing...", spinner="dots"):
            try:
                response = orchestrator.process_user_message(user_input)
            except Exception as e:
                console.print(f"\n[red]Error: {e}[/red]")
                console.print("[yellow]Please try again or type 'quit' to exit.[/yellow]\n")
                continue

        # Print response
        console.print(f"\n[bold cyan]Assistant:[/bold cyan] {response}\n")

        # Show debug info if requested
        if args.debug:
            print_schema_debug(orchestrator.get_schema())

        # Show full JSON if verbose
        if args.verbose:
            console.print("\n[dim]═══ Full Schema JSON ═══[/dim]")
            console.print_json(data=orchestrator.get_schema())
            console.print("[dim]═══════════════════════[/dim]\n")

        # Check if ready for teaching
        if orchestrator.schema.teaching_recommendation.ready:
            console.print("\n[bold green]Discovery complete! Ready to begin learning phase.[/bold green]")
            console.print(f"[dim]Topic: {orchestrator.schema.teaching_recommendation.target_topic}[/dim]")
            console.print(f"[dim]Focus: {orchestrator.schema.teaching_recommendation.focus_question}[/dim]\n")
            break

    # End session
    orchestrator.end_session()

    console.print("[dim]Conversation ended. Profile saved.[/dim]\n")


if __name__ == "__main__":
    main()
