"""Routes suggestions to appropriate chat channels."""
import sys
from pathlib import Path
from typing import Optional, Dict, List, Any, Callable
from datetime import datetime
from dataclasses import dataclass, field
import asyncio

# Add parent directory to path to import from src
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.database.manager import DatabaseManager


@dataclass
class SuggestionPayload:
    """Payload for a suggestion to be routed."""
    content: str
    source: str  # "terminal_observation", "document_analysis", "user_input"
    message_type: str = "suggestion"  # "suggestion", "observation", "task_proposal"
    metadata: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0  # 0-10


class SuggestionRouter:
    """Routes suggestions to appropriate chat channels based on bindings."""

    def __init__(self, db: DatabaseManager):
        self.db = db
        self._channel_callbacks: Dict[int, List[Callable]] = {}  # channel_id -> list of callbacks

    def register_channel_callback(self, channel_id: int, callback: Callable):
        """Register a WebSocket callback for a channel."""
        if channel_id not in self._channel_callbacks:
            self._channel_callbacks[channel_id] = []
        self._channel_callbacks[channel_id].append(callback)

    def unregister_channel_callback(self, channel_id: int, callback: Callable):
        """Unregister a WebSocket callback."""
        if channel_id in self._channel_callbacks:
            self._channel_callbacks[channel_id] = [
                cb for cb in self._channel_callbacks[channel_id] if cb != callback
            ]

    async def route_suggestion(
        self,
        goal_id: int,
        suggestion: SuggestionPayload
    ) -> List[Dict[str, Any]]:
        """Route a suggestion to the appropriate channel(s)."""
        routed_messages = []

        # Determine source binding type
        source_binding = self._get_source_binding(suggestion.source)

        # Get channels that should receive this suggestion
        channels = self._get_target_channels(goal_id, source_binding)

        for channel in channels:
            # Check if suggestion matches channel's context
            if self._matches_channel_context(suggestion, channel):
                # Save message to database
                message = self.db.create_channel_message(
                    channel_id=channel["id"],
                    role="assistant",
                    content=suggestion.content,
                    message_type=suggestion.message_type,
                    source=suggestion.source,
                    metadata=suggestion.metadata
                )

                routed_messages.append(message)

                # Notify WebSocket callbacks
                await self._notify_channel(channel["id"], message)

        return routed_messages

    def _get_source_binding(self, source: str) -> str:
        """Map suggestion source to source binding type."""
        mapping = {
            "terminal_observation": "terminal",
            "document_analysis": "document",
            "user_input": None,  # Goes to main channel
        }
        return mapping.get(source)

    def _get_target_channels(
        self,
        goal_id: int,
        source_binding: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Get channels that should receive suggestions from this source."""
        channels = []

        if source_binding:
            # Get channels bound to this specific source
            bound_channels = self.db.get_channels_by_source_binding(goal_id, source_binding)
            channels.extend(bound_channels)

            # Also get channels bound to "both"
            both_channels = self.db.get_channels_by_source_binding(goal_id, "both")
            channels.extend(both_channels)
        else:
            # Get main channel for user input
            all_channels = self.db.get_goal_channels(goal_id)
            channels = [c for c in all_channels if c["channel_type"] == "main"]

        return channels

    def _matches_channel_context(
        self,
        suggestion: SuggestionPayload,
        channel: Dict[str, Any]
    ) -> bool:
        """Check if suggestion matches channel's suggestion context."""
        context = channel.get("suggestion_context", {})

        if not context:
            return True  # No filtering

        # Check excluded topics
        excluded = context.get("excluded_topics", [])
        content_lower = suggestion.content.lower()
        for topic in excluded:
            if topic.lower() in content_lower:
                return False

        # Check focus areas (if any, suggestion must match at least one)
        focus_areas = context.get("focus_areas", [])
        if focus_areas:
            matched = any(
                area.lower() in content_lower
                for area in focus_areas
            )
            if not matched:
                return False

        return True

    async def _notify_channel(self, channel_id: int, message: Dict[str, Any]):
        """Notify WebSocket callbacks for a channel."""
        callbacks = self._channel_callbacks.get(channel_id, [])
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(message)
                else:
                    callback(message)
            except Exception as e:
                print(f"[SuggestionRouter] Callback error for channel {channel_id}: {e}")

    async def route_terminal_observation(
        self,
        goal_id: int,
        observation: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Route a terminal observation to appropriate channels."""
        # Format observation as suggestion
        content = self._format_terminal_observation(observation)

        suggestion = SuggestionPayload(
            content=content,
            source="terminal_observation",
            message_type="observation",
            metadata={
                "observation": observation,
                "timestamp": datetime.utcnow().isoformat()
            },
            priority=observation.get("priority", 0)
        )

        return await self.route_suggestion(goal_id, suggestion)

    def _format_terminal_observation(self, observation: Dict[str, Any]) -> str:
        """Format a terminal observation as readable content."""
        parts = []

        trigger = observation.get("trigger_observation", {})
        if trigger.get("is_error"):
            parts.append(f"I noticed an error: {trigger.get('error_summary', 'Unknown error')}")
            if trigger.get("command"):
                parts.append(f"Command: `{trigger['command']}`")
        elif trigger.get("command"):
            parts.append(f"I see you ran: `{trigger['command']}`")

        topics = trigger.get("topics", [])
        if topics:
            parts.append(f"This relates to: {', '.join(topics)}")

        summary = observation.get("summary", {})
        if summary.get("has_errors"):
            error_count = len(summary.get("error_summaries", []))
            if error_count > 1:
                parts.append(f"I've noticed {error_count} errors in your recent commands.")

        # Add learning-focused context
        learning_opp = trigger.get("learning_opportunity")
        if learning_opp:
            parts.append(f"This could be a good moment to explore: **{learning_opp}**")

        understanding = trigger.get("understanding_signal")
        if understanding == "struggling":
            parts.append("It looks like you're hitting some friction — want me to help break down what's happening?")
        elif understanding == "copying":
            parts.append("I see you're using AI assistance. Want to understand what the generated code is doing?")
        elif understanding == "exploring":
            parts.append("Looks like you're investigating — I can provide background on what you're looking at.")

        # Include broader learning opportunities from recent activity
        learning_opps = summary.get("learning_opportunities", [])
        if learning_opps and not learning_opp:
            parts.append(f"Topics worth exploring based on your recent activity: {', '.join(learning_opps[:3])}")

        if not parts:
            return "I'm observing your terminal activity."

        return "\n".join(parts)

    async def route_document_suggestions(
        self,
        goal_id: int,
        document_id: int,
        suggestions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Route document suggestions to appropriate channels."""
        routed = []

        for suggestion_data in suggestions:
            content = self._format_document_suggestion(suggestion_data)

            suggestion = SuggestionPayload(
                content=content,
                source="document_analysis",
                message_type="suggestion",
                metadata={
                    "document_id": document_id,
                    "suggestion_type": suggestion_data.get("suggestion_type"),
                    "location": suggestion_data.get("location"),
                    "confidence": suggestion_data.get("confidence", 0.5)
                },
                priority=int(suggestion_data.get("confidence", 0.5) * 10)
            )

            messages = await self.route_suggestion(goal_id, suggestion)
            routed.extend(messages)

        return routed

    def _format_document_suggestion(self, suggestion: Dict[str, Any]) -> str:
        """Format a document suggestion as readable content."""
        suggestion_type = suggestion.get("suggestion_type", "general")
        text = suggestion.get("text", "")
        location = suggestion.get("location")

        prefix = {
            "formatting": "Formatting suggestion",
            "content": "Content suggestion",
            "task": "Learning opportunity",
            "general": "Suggestion",
        }.get(suggestion_type, "Suggestion")

        if location:
            return f"**{prefix}** ({location}):\n{text}"
        return f"**{prefix}**:\n{text}"

    async def route_task_proposal(
        self,
        goal_id: int,
        task: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Route a learning task proposal to appropriate channels."""
        content = self._format_task_proposal(task)

        suggestion = SuggestionPayload(
            content=content,
            source=task.get("source", "document_analysis"),
            message_type="task_proposal",
            metadata={
                "task": task,
                "timestamp": datetime.utcnow().isoformat()
            },
            priority={"high": 8, "medium": 5, "low": 2}.get(task.get("priority", "low"), 2)
        )

        return await self.route_suggestion(goal_id, suggestion)

    def _format_task_proposal(self, task: Dict[str, Any]) -> str:
        """Format a task proposal as readable content."""
        topic = task.get("topic", "this topic")
        relevance = task.get("relevance", "")
        depth = task.get("suggested_depth", "10min")

        parts = [f"Would you like to learn about **{topic}**?"]

        if relevance:
            parts.append(f"*{relevance}*")

        parts.append(f"Estimated time: {depth}")

        return "\n".join(parts)


# Factory function
def create_suggestion_router(db: DatabaseManager) -> SuggestionRouter:
    """Create a new suggestion router."""
    return SuggestionRouter(db)
