"""Orchestrates agent run lifecycle: plan steps, execute, log, pause/resume."""

import logging
import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Callable, Awaitable, Dict, Optional

import os
from backend.database import AgentRun, Artifact, UserProfile, Project, get_session_factory
from backend.services.claude_code_executor import executor
from backend.services.event_store import event_store
from backend.services.prompt_builder import build_system_prompt, build_instruction, prompt_hash, classify_task
from backend.services.user_model_service import user_model_service
from backend.services.mediator import synthesize_result

logger = logging.getLogger(__name__)

EventCallback = Callable[[str, dict], Awaitable[None]]


class RunManager:
    """Manages the lifecycle of agent runs."""

    def __init__(self):
        self._active_runs: Dict[str, asyncio.Task] = {}
        self._cleanup_done = False

    def cleanup_orphaned_runs(self):
        """Mark any runs stuck in 'planning'/'working' as failed on startup.

        This handles the case where the backend was restarted while runs were in progress.
        Those runs no longer have active subprocesses, so they should be marked failed.
        """
        if self._cleanup_done:
            return
        self._cleanup_done = True

        session = get_session_factory()()
        try:
            orphaned = (
                session.query(AgentRun)
                .filter(AgentRun.status.in_(["planning", "working"]))
                .all()
            )
            if orphaned:
                logger.info(f"Cleaning up {len(orphaned)} orphaned runs from previous session")
                for run in orphaned:
                    run.status = "failed"
                    run.completed_at = datetime.now(timezone.utc)
                    run.result_summary = (run.result_summary or "") + "\n[Run interrupted by server restart]"
                session.commit()
        except Exception as e:
            logger.warning(f"Failed to cleanup orphaned runs: {e}")
        finally:
            session.close()

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

                # Classify task type and append specialized prompt
                from backend.prompts.executor import TASK_PROMPTS
                task_type = classify_task(run.goal, has_prior_runs=len(recent_runs) > 0)
                task_section = TASK_PROMPTS.get(task_type, TASK_PROMPTS["content"])
                system_prompt = f"{system_prompt}\n\n{task_section}"
                logger.info(f"Run {run_id}: task_type={task_type}")

                from backend.services.context_service import get_context_text
                ctx = get_context_text(session, user.id, project_id=project.id)
                instruction = build_instruction(user, project, run.goal, recent_runs, context_text=ctx)
                run.enriched_instruction = instruction
                run.system_prompt_hash = prompt_hash(system_prompt)

            run.status = "working"
            run.started_at = datetime.now(timezone.utc)
            session.commit()

            if on_event:
                await on_event(run_id, {"type": "status", "status": "working"})

            result_parts = []
            written_html_files = []
            written_other_files = []
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
                    # Intermediate assistant text - only add if not duplicate
                    text = ev.content.get("text", "")
                    if text and (not result_parts or result_parts[-1] != text):
                        result_parts.append(text)
                elif ev.type == "tool_use":
                    # Capture file writes — HTML for app artifacts, others for synthesis
                    tools = ev.content.get("tools", [])
                    for t in tools:
                        tool_name = t.get("tool", "")
                        tool_input = t.get("input", {})
                        if tool_name == "Write":
                            file_path = tool_input.get("file_path", "") or tool_input.get("path", "")
                            content = tool_input.get("content", "")
                            if file_path and content:
                                if file_path.endswith(".html"):
                                    written_html_files.append({"path": file_path, "content": content})
                                else:
                                    written_other_files.append({"path": file_path, "content": content[:5000]})
                elif ev.type == "result":
                    # Final result - only add if not duplicate
                    text = ev.content.get("text", "")
                    if text and (not result_parts or result_parts[-1] != text):
                        result_parts.append(text)
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

            # Create app artifacts from captured HTML files (deduplicated)
            if run.status == "done" and project and written_html_files:
                seen_hashes = set()
                deduped = []
                for f in written_html_files:
                    content_hash = hashlib.sha256(f["content"].encode()).hexdigest()[:16]
                    if content_hash not in seen_hashes:
                        seen_hashes.add(content_hash)
                        deduped.append(f)
                for f in deduped:
                    title = os.path.basename(f["path"]).replace(".html", "").replace("-", " ").replace("_", " ").title()
                    artifact = Artifact(
                        run_id=run_id,
                        project_id=project.id,
                        artifact_type="app",
                        title=title,
                        content={"html": f["content"]},
                        sources=[],
                    )
                    session.add(artifact)
                session.commit()
                logger.info(f"Created {len(deduped)} app artifact(s) for run {run_id} (deduped from {len(written_html_files)})")

            # Update user model after successful completion
            if run.status == "done" and user:
                try:
                    await user_model_service.update_model(run.user_id)
                except Exception as e:
                    logger.warning(f"Failed to update user model after run {run_id}: {e}")

                # Synthesize results before broadcasting done
                try:
                    synthesis = synthesize_result(run, project, user, session, written_files=written_other_files)
                    # Flush artifacts to DB before broadcasting so workspace refresh finds them
                    session.commit()
                    if on_event:
                        await on_event(run_id, {
                            "type": "synthesis",
                            "summary": synthesis["summary"],
                            "full_output": run.result_summary,
                            "artifacts": synthesis["artifacts"],
                            "suggested_next_steps": synthesis["suggested_next_steps"],
                            "actions": synthesis["actions"],
                        })
                except Exception as e:
                    logger.warning(f"Synthesis failed for run {run_id}: {e}")

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
