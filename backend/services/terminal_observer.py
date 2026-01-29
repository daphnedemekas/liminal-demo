"""AI observation layer for terminal activity.

Observes terminal commands and output to:
- Detect what the user is building/working on
- Identify potential confusion or errors
- Suggest learning opportunities based on the tools and patterns they use
- Track whether the user understands what their code is doing
- Balance curiosity/motivation with actual learning needs
"""
import sys
import re
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, field

sys.path.append(str(Path(__file__).parent.parent.parent))


@dataclass
class CommandObservation:
    """Observation from a terminal command."""
    command: str
    output: str
    exit_code: int
    timestamp: str
    activity_type: str  # "claude_code", "git", "npm", "python", "shell", "unknown"
    is_error: bool = False
    error_summary: Optional[str] = None
    topics_detected: List[str] = field(default_factory=list)
    should_trigger_suggestion: bool = False
    suggestion_priority: int = 0  # 0-10, higher = more urgent
    learning_opportunity: Optional[str] = None  # What the user might learn from this
    understanding_signal: Optional[str] = None  # "confident", "exploring", "struggling", "copying"


class TerminalObserver:
    """AI observation layer for terminal activity."""

    # Patterns to detect different activity types
    ACTIVITY_PATTERNS = {
        "claude_code": [
            r"^claude\s+",
            r"^claude-code\s+",
            r"^cc\s+",
        ],
        "git": [
            r"^git\s+",
            r"^gh\s+",
        ],
        "npm": [
            r"^npm\s+",
            r"^yarn\s+",
            r"^pnpm\s+",
            r"^npx\s+",
        ],
        "python": [
            r"^python[23]?\s+",
            r"^pip[23]?\s+",
            r"^poetry\s+",
            r"^pytest\s+",
            r"^uv\s+",
        ],
        "docker": [
            r"^docker\s+",
            r"^docker-compose\s+",
        ],
        "build": [
            r"^make\s+",
            r"^cargo\s+",
            r"^go\s+(build|run|test)",
            r"^mvn\s+",
            r"^gradle\s+",
        ],
        "shell": [
            r"^(ls|cd|pwd|cat|grep|find|sed|awk|head|tail|less|more)\s*",
            r"^(mkdir|rm|cp|mv|touch|chmod|chown)\s+",
            r"^(curl|wget|ssh|scp)\s+",
        ],
    }

    # Patterns that indicate errors
    ERROR_PATTERNS = [
        r"error:",
        r"Error:",
        r"ERROR:",
        r"failed",
        r"Failed",
        r"FAILED",
        r"exception",
        r"Exception",
        r"traceback",
        r"Traceback",
        r"command not found",
        r"No such file or directory",
        r"Permission denied",
        r"fatal:",
        r"panic:",
    ]

    # Topics that might trigger learning suggestions
    LEARNING_TOPICS = {
        "async": ["async", "await", "promise", "asyncio", "concurrent"],
        "testing": ["test", "pytest", "jest", "unittest", "spec"],
        "debugging": ["debug", "breakpoint", "pdb", "debugger"],
        "git_workflow": ["merge", "rebase", "branch", "stash", "conflict"],
        "deployment": ["deploy", "kubernetes", "k8s", "docker", "container"],
        "security": ["auth", "token", "secret", "password", "encryption"],
        "performance": ["profile", "optimize", "benchmark", "memory", "cpu"],
        "database": ["sql", "query", "migration", "schema", "index"],
        "api": ["api", "rest", "graphql", "endpoint", "request", "response"],
    }

    def __init__(self, debounce_seconds: float = 2.0):
        self.debounce_seconds = debounce_seconds
        self.observation_buffer: List[CommandObservation] = []
        self.last_suggestion_time: Optional[datetime] = None
        self.suggestion_cooldown_seconds = 10.0

    def detect_activity_type(self, command: str) -> str:
        """Detect the type of activity from a command."""
        command = command.strip()

        for activity_type, patterns in self.ACTIVITY_PATTERNS.items():
            for pattern in patterns:
                if re.match(pattern, command, re.IGNORECASE):
                    return activity_type

        return "unknown"

    def is_error_output(self, output: str, exit_code: int) -> Tuple[bool, Optional[str]]:
        """Check if output indicates an error."""
        if exit_code != 0:
            # Find error summary from output
            for line in output.split("\n"):
                for pattern in self.ERROR_PATTERNS:
                    if re.search(pattern, line, re.IGNORECASE):
                        return True, line.strip()[:200]
            return True, f"Command exited with code {exit_code}"

        # Check output for error patterns even if exit code is 0
        for line in output.split("\n"):
            for pattern in self.ERROR_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    return True, line.strip()[:200]

        return False, None

    def detect_topics(self, command: str, output: str) -> List[str]:
        """Detect learning topics from command and output."""
        detected = []
        combined_text = f"{command} {output}".lower()

        for topic, keywords in self.LEARNING_TOPICS.items():
            for keyword in keywords:
                if keyword in combined_text:
                    detected.append(topic)
                    break

        return detected

    def _detect_understanding_signal(self, command: str, output: str, is_error: bool, activity_type: str) -> Optional[str]:
        """Detect the user's likely understanding level from their terminal behavior."""
        cmd_lower = command.strip().lower()

        # Rapid repeated commands with errors → struggling
        recent_errors = sum(1 for obs in self.observation_buffer[-5:] if obs.is_error)
        if recent_errors >= 3:
            return "struggling"

        # Claude Code usage → might be copying without understanding
        if activity_type == "claude_code":
            return "copying"

        # Running tests after changes → confident workflow
        if any(p in cmd_lower for p in ["pytest", "jest", "npm test", "cargo test", "go test"]):
            return "confident"

        # Exploratory commands (ls, cat, grep, find, help, man) → exploring
        if any(p in cmd_lower for p in ["--help", "man ", "cat ", "less ", "grep ", "find "]):
            return "exploring"

        # Git workflow commands → likely understands what they're doing
        if activity_type == "git" and any(p in cmd_lower for p in ["commit", "push", "merge"]):
            return "confident"

        return None

    def _detect_learning_opportunity(self, command: str, output: str, is_error: bool, topics: List[str]) -> Optional[str]:
        """Detect what the user might benefit from learning."""
        cmd_lower = command.strip().lower()

        if is_error:
            # Error-specific learning opportunities
            if "permission denied" in output.lower():
                return "File permissions and access control"
            if "module not found" in output.lower() or "no module named" in output.lower():
                return "Package management and dependency resolution"
            if "syntax error" in output.lower():
                return "Language syntax patterns"
            if "merge conflict" in output.lower():
                return "Git merge conflict resolution strategies"
            return f"Debugging {topics[0] if topics else 'this type of error'}"

        # Tool-specific learning
        if "docker" in cmd_lower and "build" in cmd_lower:
            return "Docker image layering and build optimization"
        if "git rebase" in cmd_lower:
            return "Git history rewriting — when and why to use rebase vs merge"
        if any(p in cmd_lower for p in ["kubectl", "k8s"]):
            return "Kubernetes orchestration concepts"

        return None

    def process_command(self, command: str, output: str, exit_code: int = 0) -> CommandObservation:
        """Process a command and create an observation."""
        activity_type = self.detect_activity_type(command)
        is_error, error_summary = self.is_error_output(output, exit_code)
        topics = self.detect_topics(command, output)

        should_trigger = self._should_trigger_suggestion(
            activity_type=activity_type,
            is_error=is_error,
            topics=topics
        )

        priority = self._calculate_suggestion_priority(
            activity_type=activity_type,
            is_error=is_error,
            topics=topics
        )

        understanding_signal = self._detect_understanding_signal(command, output, is_error, activity_type)
        learning_opportunity = self._detect_learning_opportunity(command, output, is_error, topics)

        observation = CommandObservation(
            command=command,
            output=output[:5000],
            exit_code=exit_code,
            timestamp=datetime.utcnow().isoformat(),
            activity_type=activity_type,
            is_error=is_error,
            error_summary=error_summary,
            topics_detected=topics,
            should_trigger_suggestion=should_trigger,
            suggestion_priority=priority,
            learning_opportunity=learning_opportunity,
            understanding_signal=understanding_signal,
        )

        # Add to buffer
        self.observation_buffer.append(observation)
        if len(self.observation_buffer) > 50:
            self.observation_buffer = self.observation_buffer[-50:]

        return observation

    def _should_trigger_suggestion(
        self,
        activity_type: str,
        is_error: bool,
        topics: List[str]
    ) -> bool:
        """Determine if this observation should trigger a suggestion."""
        # Check cooldown
        if self.last_suggestion_time:
            elapsed = (datetime.utcnow() - self.last_suggestion_time).total_seconds()
            if elapsed < self.suggestion_cooldown_seconds:
                return False

        # Always suggest on errors
        if is_error:
            return True

        # Suggest for Claude Code interactions
        if activity_type == "claude_code":
            return True

        # Suggest if learning topics detected
        if len(topics) >= 2:
            return True

        return False

    def _calculate_suggestion_priority(
        self,
        activity_type: str,
        is_error: bool,
        topics: List[str]
    ) -> int:
        """Calculate priority for a suggestion (0-10)."""
        priority = 0

        if is_error:
            priority += 5

        if activity_type == "claude_code":
            priority += 3
        elif activity_type in ("git", "npm", "python"):
            priority += 1

        priority += min(len(topics), 3)

        return min(priority, 10)

    def get_observation_summary(self, max_commands: int = 10) -> Dict[str, Any]:
        """Get a summary of recent observations for AI context."""
        recent = self.observation_buffer[-max_commands:] if self.observation_buffer else []

        if not recent:
            return {
                "has_activity": False,
                "command_count": 0,
                "recent_commands": [],
                "activity_types": [],
                "topics_detected": [],
                "has_errors": False,
                "error_summaries": [],
            }

        activity_types = list(set(obs.activity_type for obs in recent))
        all_topics = []
        for obs in recent:
            all_topics.extend(obs.topics_detected)
        topics = list(set(all_topics))

        errors = [obs for obs in recent if obs.is_error]
        error_summaries = [obs.error_summary for obs in errors if obs.error_summary]

        # Detect overall understanding pattern
        understanding_signals = [obs.understanding_signal for obs in recent if obs.understanding_signal]
        learning_opportunities = [obs.learning_opportunity for obs in recent if obs.learning_opportunity]

        return {
            "has_activity": True,
            "command_count": len(recent),
            "recent_commands": [
                {
                    "command": obs.command[:200],
                    "activity_type": obs.activity_type,
                    "is_error": obs.is_error,
                    "timestamp": obs.timestamp,
                }
                for obs in recent
            ],
            "activity_types": activity_types,
            "topics_detected": topics,
            "has_errors": len(errors) > 0,
            "error_summaries": error_summaries[:5],
            "understanding_signals": understanding_signals[-5:],
            "learning_opportunities": list(set(learning_opportunities))[:5],
        }

    def should_trigger_suggestion_now(self) -> bool:
        """Check if we should send a suggestion based on recent activity."""
        if not self.observation_buffer:
            return False

        # Check the most recent observation
        latest = self.observation_buffer[-1]
        if not latest.should_trigger_suggestion:
            return False

        # Mark that we're sending a suggestion
        self.last_suggestion_time = datetime.utcnow()
        return True

    def get_suggestion_context(self) -> Dict[str, Any]:
        """Get context for generating a suggestion."""
        summary = self.get_observation_summary()

        # Find the highest priority observation
        max_priority = 0
        trigger_observation = None
        for obs in reversed(self.observation_buffer[-10:]):
            if obs.suggestion_priority > max_priority:
                max_priority = obs.suggestion_priority
                trigger_observation = obs

        return {
            "summary": summary,
            "trigger_observation": {
                "command": trigger_observation.command if trigger_observation else None,
                "is_error": trigger_observation.is_error if trigger_observation else False,
                "error_summary": trigger_observation.error_summary if trigger_observation else None,
                "topics": trigger_observation.topics_detected if trigger_observation else [],
                "learning_opportunity": trigger_observation.learning_opportunity if trigger_observation else None,
                "understanding_signal": trigger_observation.understanding_signal if trigger_observation else None,
            },
            "priority": max_priority,
        }

    def clear_buffer(self):
        """Clear the observation buffer."""
        self.observation_buffer = []


# Factory function to create observers
def create_terminal_observer(debounce_seconds: float = 2.0) -> TerminalObserver:
    """Create a new terminal observer instance."""
    return TerminalObserver(debounce_seconds=debounce_seconds)
