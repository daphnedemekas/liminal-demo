"""Wraps Claude Code CLI, parses stream-json output, logs events."""

import asyncio
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import AsyncIterator, List, Optional
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

    from backend.prompts.executor import EXECUTOR_SYSTEM_PROMPT as SYSTEM_PROMPT

    async def execute(
        self,
        instruction: str,
        system_prompt: Optional[str] = None,
        working_dir: str = ".",
        allowed_tools: Optional[List[str]] = None,
        max_turns: Optional[int] = None,
    ) -> AsyncIterator[ExecutorEvent]:
        """
        Run a single Claude Code instruction and yield parsed events.

        Uses: claude -p "instruction" --output-format stream-json --verbose
        """
        # Use --strict-mcp-config with empty config to prevent user-level
        # MCP servers (e.g. Playwright) from loading, while keeping HOME
        # intact so the CLI can find its auth credentials.
        sandbox_home = tempfile.mkdtemp(prefix="envisage-sandbox-")
        empty_mcp_config = Path(sandbox_home) / "empty-mcp.json"
        empty_mcp_config.write_text(json.dumps({"mcpServers": {}}))

        cmd = [
            "claude", "-p", instruction,
            "--output-format", "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
            "--system-prompt", system_prompt or self.SYSTEM_PROMPT,
            "--mcp-config", str(empty_mcp_config),
            "--strict-mcp-config",
        ]

        if allowed_tools:
            cmd.extend(["--allowedTools", ",".join(allowed_tools)])
        if max_turns is not None:
            cmd.extend(["--max-turns", str(max_turns)])

        env = os.environ.copy()

        logger.info(f"Executing claude: {instruction[:100]}...")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        try:
            async for line in process.stdout:
                line = line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    for event in self._parse_events(data):
                        yield event
                except json.JSONDecodeError:
                    logger.warning(f"Non-JSON line from claude: {line[:200]}")
        except GeneratorExit:
            # Generator was closed (e.g. by timeout/cancellation) — kill the process
            logger.info("Executor generator closed, killing subprocess")
            process.kill()
            await process.wait()
            return
        except Exception as e:
            yield ExecutorEvent(type="error", content={"error": str(e)}, raw={})

        await process.wait()

        # Clean up sandbox HOME directory
        try:
            shutil.rmtree(sandbox_home, ignore_errors=True)
        except Exception:
            pass

        if process.returncode != 0:
            stderr = await process.stderr.read()
            err_msg = stderr.decode("utf-8").strip() if stderr else "Unknown error"
            yield ExecutorEvent(
                type="error",
                content={"error": err_msg, "exit_code": process.returncode},
                raw={},
            )

    def _parse_events(self, data: dict) -> List[ExecutorEvent]:
        """Parse a stream-json line into one or more ExecutorEvents."""
        msg_type = data.get("type", "")
        events: List[ExecutorEvent] = []

        if msg_type == "system":
            events.append(ExecutorEvent(
                type="system",
                content={"session_id": data.get("session_id", "")},
                raw=data,
            ))

        elif msg_type == "assistant":
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

            # Emit text first, then tool uses — so both appear in activity log
            if text_parts:
                events.append(ExecutorEvent(
                    type="assistant",
                    content={"text": "\n".join(text_parts)},
                    raw=data,
                ))

            if tool_uses:
                events.append(ExecutorEvent(
                    type="tool_use",
                    content={"tools": tool_uses},
                    raw=data,
                ))

        elif msg_type == "result":
            usage = data.get("usage", {})
            events.append(ExecutorEvent(
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
            ))

        else:
            logger.debug(f"Unhandled stream event type: {msg_type}")

        return events


executor = ClaudeCodeExecutor()
