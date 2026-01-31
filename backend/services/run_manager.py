"""Orchestrates agent run lifecycle: plan steps, execute, log, pause/resume."""

import logging
import asyncio
from datetime import datetime, timezone
from typing import Callable, Awaitable, Dict, Optional

from backend.database import AgentRun, UserProfile, Project, get_session_factory
from backend.services.claude_code_executor import executor
from backend.services.event_store import event_store
from backend.services.prompt_builder import build_system_prompt, build_instruction, prompt_hash
from backend.services.user_model_service import user_model_service

logger = logging.getLogger(__name__)

EventCallback = Callable[[str, dict], Awaitable[None]]


class RunManager:
    """Manages the lifecycle of agent runs."""

    def __init__(self):
        self._active_runs: Dict[str, asyncio.Task] = {}

    async def start_run(self, run_id: str, on_event: Optional[EventCallback] = None):
        if run_id in self._active_runs:
            logger.warning(f"Run {run_id} already active")
            return
        task = asyncio.create_task(self._execute_run(run_id, on_event))
        self._active_runs[run_id] = task

    async def stop_run(self, run_id: str):
        task = self._active_runs.pop(run_id, None)
        if task:
            task.cancel()
            self._update_status(run_id, "failed")

    async def _execute_run(self, run_id: str, on_event: Optional[EventCallback]):
        session = get_session_factory()()
        try:
            run = session.query(AgentRun).filter_by(run_id=run_id).first()
            if not run:
                logger.error(f"Run {run_id} not found")
                return

            # Build personalized prompt
            project = session.query(Project).filter_by(id=run.project_id).first()
            user = session.query(UserProfile).filter_by(id=run.user_id).first()

            system_prompt = None
            instruction = run.goal

            if user and project:
                recent_runs = (
                    session.query(AgentRun)
                    .filter_by(project_id=run.project_id)
                    .filter(AgentRun.run_id != run_id)
                    .order_by(AgentRun.created_at.desc())
                    .limit(3)
                    .all()
                )
                system_prompt = build_system_prompt(user, project)
                instruction = build_instruction(user, project, run.goal, recent_runs)
                run.enriched_instruction = instruction
                run.system_prompt_hash = prompt_hash(system_prompt)

            run.status = "working"
            run.started_at = datetime.now(timezone.utc)
            session.commit()

            if on_event:
                await on_event(run_id, {"type": "status", "status": "working"})

            result_parts = []
            has_error = False
            async for ev in executor.execute(
                instruction=instruction,
                system_prompt=system_prompt,
                working_dir=".",
            ):
                event_store.log(
                    run_id=run_id,
                    event_type=ev.type,
                    payload=ev.content,
                    source_url=ev.content.get("source_url"),
                    source_title=ev.content.get("source_title"),
                )

                if on_event:
                    await on_event(run_id, {
                        "type": "event",
                        "event_type": ev.type,
                        "content": ev.content,
                    })

                if ev.type == "assistant":
                    result_parts.append(ev.content.get("text", ""))
                elif ev.type == "result":
                    result_parts.append(ev.content.get("text", ""))
                    cost_usd = ev.content.get("cost_usd", 0)
                    run.cost_cents = int(float(cost_usd) * 100) if cost_usd else 0
                    run.token_usage = ev.content.get("tokens", {})
                    if ev.content.get("is_error"):
                        has_error = True
                elif ev.type == "error":
                    has_error = True

            run.status = "failed" if has_error else "done"
            run.completed_at = datetime.now(timezone.utc)
            run.result_summary = "\n".join(result_parts)
            session.commit()

            # Update user model after successful completion
            if run.status == "done" and user:
                try:
                    await user_model_service.update_model(run.user_id)
                except Exception as e:
                    logger.warning(f"Failed to update user model after run {run_id}: {e}")

            if on_event:
                await on_event(run_id, {
                    "type": "status",
                    "status": "done",
                    "result_summary": run.result_summary,
                })

        except asyncio.CancelledError:
            logger.info(f"Run {run_id} cancelled")
            self._update_status(run_id, "failed")
        except Exception as e:
            logger.exception(f"Run {run_id} failed: {e}")
            self._update_status(run_id, "failed")
            event_store.log(run_id, "error", {"error": str(e)})
            if on_event:
                await on_event(run_id, {"type": "error", "error": str(e)})
        finally:
            session.close()
            self._active_runs.pop(run_id, None)

    def _update_status(self, run_id: str, status: str):
        session = get_session_factory()()
        try:
            run = session.query(AgentRun).filter_by(run_id=run_id).first()
            if run:
                run.status = status
                if status in ("done", "failed"):
                    run.completed_at = datetime.now(timezone.utc)
                session.commit()
        finally:
            session.close()


run_manager = RunManager()
