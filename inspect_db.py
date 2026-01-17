#!/usr/bin/env python3
"""
Database inspection tool for Liminal discovery system.
Shows what's stored in the SQLite database.
"""
import json
from src.database.manager import DatabaseManager
from rich.console import Console
from rich.table import Table

console = Console()


def main():
    db = DatabaseManager()

    console.print("\n[bold]Liminal Database Inspector[/bold]\n")

    # Get all users
    from src.database.models import UserProfile, ConversationSession
    session = db._get_session()

    try:
        users = session.query(UserProfile).all()

        if not users:
            console.print("[yellow]No users found in database.[/yellow]")
            return

        # User profiles table
        console.print(f"[bold]Users ({len(users)}):[/bold]\n")
        user_table = Table(show_header=True, header_style="bold")
        user_table.add_column("User ID")
        user_table.add_column("Sessions")
        user_table.add_column("Topics Explored")
        user_table.add_column("Curiosity Type")
        user_table.add_column("Created")

        for user in users:
            curiosity = user.curiosity_type.get('value', 'unknown') if user.curiosity_type else 'unknown'
            user_table.add_row(
                user.user_id[:12] + "...",
                str(user.total_sessions),
                str(user.total_topics_explored),
                curiosity,
                user.created_at.strftime("%Y-%m-%d %H:%M")
            )

        console.print(user_table)

        # For each user, show detailed profile
        for user in users:
            console.print(f"\n[bold cyan]User: {user.user_id}[/bold cyan]")

            console.print("\n[bold]Profile Dimensions:[/bold]")
            console.print(f"  Curiosity Type: {json.dumps(user.curiosity_type, indent=2)}")
            console.print(f"  Entry Mode: {json.dumps(user.entry_mode, indent=2)}")
            console.print(f"  Uncertainty Tolerance: {json.dumps(user.uncertainty_tolerance, indent=2)}")
            console.print(f"  Motivation: {json.dumps(user.motivation_profile, indent=2)}")
            console.print(f"  RIASEC: {json.dumps(user.riasec_hint, indent=2)}")

            # Show sessions
            sessions = session.query(ConversationSession).filter_by(user_id=user.user_id).all()
            if sessions:
                console.print(f"\n[bold]Sessions ({len(sessions)}):[/bold]")
                for sess in sessions:
                    console.print(f"\n  Session: {sess.session_id[:12]}...")
                    console.print(f"    Started: {sess.started_at.strftime('%Y-%m-%d %H:%M')}")
                    console.print(f"    Turns: {sess.turns_elapsed}")
                    console.print(f"    Topics Mentioned: {sess.topics_mentioned}")
                    if sess.final_topic:
                        console.print(f"    Final Topic: {sess.final_topic}")

                    # Show last schema state
                    if sess.schema_state:
                        console.print(f"\n    Last Schema State:")
                        console.print(f"      Topics: {len(sess.schema_state.get('topic_candidates', []))}")
                        console.print(f"      Signals: {len(sess.schema_state.get('signals', []))}")
                        console.print(f"      Confidence in Profile: {sess.schema_state.get('interview_state', {}).get('confidence_in_profile', 0):.2f}")
                        console.print(f"      Ready for Teaching: {sess.schema_state.get('teaching_recommendation', {}).get('ready', False)}")

            # Show signals
            signals = user.signals
            if signals:
                console.print(f"\n[bold]Signals Extracted ({len(signals)}):[/bold]")
                for sig in signals[-5:]:  # Last 5
                    console.print(f"  - Turn {sig.turn}: {sig.signal_type} (conf: {sig.confidence:.2f})")
                    console.print(f"    \"{sig.evidence_quote[:80]}...\"")
                    console.print(f"    Updates: {sig.updates_field}")

            console.print("\n" + "="*80 + "\n")

    finally:
        session.close()


if __name__ == "__main__":
    main()
