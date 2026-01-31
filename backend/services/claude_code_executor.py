"""Wraps Claude Code CLI, parses stream-json output, logs events."""

import asyncio
import json
import logging
from typing import AsyncIterator
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ExecutorEvent:
    """Parsed event from Claude Code CLI output."""
    type: str  # assistant | tool_use | result | error | system
    content: dict
    raw: dict


class ClaudeCodeExecutor:
    """Executes instructions via Claude Code CLI and streams structured events."""

    SYSTEM_PROMPT = (
        "You are Liminal, a helpful general-purpose AI assistant. "
        "You help users with anything they need: research, planning, analysis, "
        "writing, organizing, learning, home projects, business tasks, and more. "
        "You are NOT limited to software engineering. "
        "You have access to web search, web browsing, file operations, and code execution. "
        "Use these tools proactively to find information, compare options, "
        "gather sources, and produce useful deliverables for the user. "
        "Always cite your sources with URLs when doing research. "
        "Be practical, thorough, and action-oriented."
    )

    async def execute(
        self,
        instruction: str,
        working_dir: str = ".",
        allowed_tools: list[str] | None = None,
        max_turns: int | None = None,
    ) -> AsyncIterator[ExecutorEvent]:
        """
        Run a single Claude Code instruction and yield parsed events.

        Uses: claude -p "instruction" --output-format stream-json --verbose
        """
        cmd = [
            "claude", "-p", instruction,
            "--output-format", "stream-json",
            "--verbose",
            "--system-prompt", self.SYSTEM_PROMPT,
        ]

        if allowed_tools:
            cmd.extend(["--allowedTools", ",".join(allowed_tools)])
        if max_turns is not None:
            cmd.extend(["--max-turns", str(max_turns)])

        logger.info(f"Executing claude: {instruction[:100]}...")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            async for line in process.stdout:
                line = line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    event = self._parse_event(data)
                    if event:
                        yield event
                except json.JSONDecodeError:
                    logger.warning(f"Non-JSON line from claude: {line[:200]}")
        except Exception as e:
            yield ExecutorEvent(type="error", content={"error": str(e)}, raw={})

        await process.wait()

        if process.returncode != 0:
            stderr = await process.stderr.read()
            err_msg = stderr.decode("utf-8").strip() if stderr else "Unknown error"
            yield ExecutorEvent(
                type="error",
                content={"error": err_msg, "exit_code": process.returncode},
                raw={},
            )

    def _parse_event(self, data: dict) -> ExecutorEvent | None:
        """Parse a stream-json line into an ExecutorEvent."""
        msg_type = data.get("type", "")

        if msg_type == "system":
            return ExecutorEvent(
                type="system",
                content={"session_id": data.get("session_id", "")},
                raw=data,
            )

        if msg_type == "assistant":
            message = data.get("message", {})
            text_parts = []
            tool_uses = []

            for block in message.get("content", []):
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tool_uses.append({
                        "tool": block.get("name", ""),
                        "input": block.get("input", {}),
                        "id": block.get("id", ""),
                    })

            # Yield tool uses first
            if tool_uses:
                return ExecutorEvent(
                    type="tool_use",
                    content={"tools": tool_uses},
                    raw=data,
                )

            if text_parts:
                return ExecutorEvent(
                    type="assistant",
                    content={"text": "\n".join(text_parts)},
                    raw=data,
                )

        elif msg_type == "result":
            usage = data.get("usage", {})
            return ExecutorEvent(
                type="result",
                content={
                    "text": data.get("result", ""),
                    "cost_usd": data.get("total_cost_usd", 0),
                    "duration_ms": data.get("duration_ms", 0),
                    "num_turns": data.get("num_turns", 0),
                    "is_error": data.get("is_error", False),
                    "tokens": {
                        "input": usage.get("input_tokens", 0),
                        "output": usage.get("output_tokens", 0),
                        "cache_read": usage.get("cache_read_input_tokens", 0),
                        "cache_creation": usage.get("cache_creation_input_tokens", 0),
                    },
                },
                raw=data,
            )

        return None


executor = ClaudeCodeExecutor()
