#!/usr/bin/env python3
"""
Safe benchmark runner that handles rate limits gracefully.

Runs each (persona, routing) combination individually, catching rate limit errors
and skipping affected models. Generates a summary report.

Usage:
    python3 benchmarks/run_benchmark_safe.py --user-model cerebras:llama-3.3-70b
    python3 benchmarks/run_benchmark_safe.py --user-model openai:gpt-4o-mini
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.orchestrator import DiscoveryOrchestrator
from src.config import reset_app_config_cache
from src.llm_client import LLMClient


# ============================================================================
# Configuration
# ============================================================================

RESULTS_DIR = Path(__file__).parent / "results" / "benchmark_runs"


@dataclass
class Persona:
    name: str
    background: str


@dataclass 
class BenchmarkResult:
    persona: str
    routing: str
    user_model: str
    status: str  # "success", "rate_limit", "error"
    error_message: Optional[str] = None
    error_provider: Optional[str] = None
    turns_completed: int = 0
    total_time_s: float = 0.0
    reached_teaching: bool = False
    final_topic: Optional[str] = None
    artifact_path: Optional[str] = None
    transcript_preview: Optional[str] = None


@dataclass
class BenchmarkSession:
    """Track state across the benchmark session."""
    blocked_providers: Set[str] = field(default_factory=set)
    results: List[BenchmarkResult] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)


# ============================================================================
# Personas
# ============================================================================

PERSONAS: List[Persona] = [
    Persona(
        name="mechanism_driven_designer",
        background=(
            "- Studied: industrial design + a minor in CS\n"
            "- Work: product designer on developer tools\n"
            "- Hobbies: photography, woodworking, synth music\n"
            "- Personality: curious, skeptical of buzzwords, likes concrete mechanisms\n"
            "- You sometimes get obsessed with understanding *why* something works\n"
        ),
    ),
    Persona(
        name="bio_to_policy_switcher",
        background=(
            "- Studied: biology (systems / ecology)\n"
            "- Work: policy / nonprofit research\n"
            "- Hobbies: running, reading history, cooking\n"
            "- Personality: reflective, values meaning/impact, likes connecting ideas\n"
            "- You often notice patterns but feel 'fuzzy' on the mechanism details\n"
        ),
    ),
    Persona(
        name="mathy_builder_with_random_interests",
        background=(
            "- Studied: applied math\n"
            "- Work: software engineer\n"
            "- Hobbies: chess, rock climbing, collecting weird facts\n"
            "- Personality: playful, likes counterintuitive ideas, hates vague explanations\n"
            "- You get excited when a niche concept suddenly 'clicks'\n"
        ),
    ),
]


# ============================================================================
# Routing Configs - Extended Set
# ============================================================================

def build_routing_configs() -> List[Dict[str, Any]]:
    """
    Extended set of routing configs to test speed vs quality tradeoffs.
    """
    return [
        # === ALL CEREBRAS (FASTEST) ===
        {
            "name": "all_cerebras_fast",
            "description": "All Cerebras - fastest, tests if speed alone works",
            "cfg": {
                "providers": {"cerebras": {"base_url": "https://api.cerebras.ai/v1"}},
                "models": {
                    "interviewer": {"name": "cerebras:llama-3.3-70b"},
                    "ranker": {
                        "name": "cerebras:llama-3.3-70b",
                        "branch_classifier": {"name": "cerebras:llama3.1-8b"},
                        "profile": {"name": "cerebras:llama-3.3-70b"},
                        "themes": {"name": "cerebras:llama-3.3-70b"},
                        "teaching_candidates": {"name": "cerebras:llama-3.3-70b"},
                        "controller": {"name": "cerebras:llama-3.3-70b"},
                        "readiness": {"name": "cerebras:llama-3.3-70b"},
                    },
                },
                "conversation": {"max_turns": 8, "min_turns_before_commit": 5},
            },
        },
        
        # === HYBRID: CEREBRAS FAST + STRONGER INTERVIEWER ===
        {
            "name": "cerebras_claude_interviewer",
            "description": "Cerebras ranker + Claude interviewer - fast analysis, quality questions",
            "cfg": {
                "providers": {"cerebras": {"base_url": "https://api.cerebras.ai/v1"}},
                "models": {
                    "interviewer": {"name": "anthropic:claude-sonnet-4-20250514"},
                    "ranker": {
                        "name": "cerebras:llama-3.3-70b",
                        "branch_classifier": {"name": "cerebras:llama3.1-8b"},
                        "profile": {"name": "cerebras:llama-3.3-70b"},
                        "themes": {"name": "cerebras:llama-3.3-70b"},
                        "teaching_candidates": {"name": "cerebras:llama-3.3-70b"},
                        "controller": {"name": "cerebras:llama-3.3-70b"},
                        "readiness": {"name": "cerebras:llama-3.3-70b"},
                    },
                },
                "conversation": {"max_turns": 8, "min_turns_before_commit": 5},
            },
        },
        
        # === HYBRID: CEREBRAS FAST + GPT-4O INTERVIEWER ===
        {
            "name": "cerebras_gpt4o_interviewer",
            "description": "Cerebras ranker + GPT-4o interviewer - fast analysis, different question style",
            "cfg": {
                "providers": {"cerebras": {"base_url": "https://api.cerebras.ai/v1"}},
                "models": {
                    "interviewer": {"name": "openai:gpt-4o"},
                    "ranker": {
                        "name": "cerebras:llama-3.3-70b",
                        "branch_classifier": {"name": "cerebras:llama3.1-8b"},
                        "profile": {"name": "cerebras:llama-3.3-70b"},
                        "themes": {"name": "cerebras:llama-3.3-70b"},
                        "teaching_candidates": {"name": "cerebras:llama-3.3-70b"},
                        "controller": {"name": "cerebras:llama-3.3-70b"},
                        "readiness": {"name": "cerebras:llama-3.3-70b"},
                    },
                },
                "conversation": {"max_turns": 8, "min_turns_before_commit": 5},
            },
        },
        
        # === HYBRID: CEREBRAS + CLAUDE CONTROLLER (critical path) ===
        {
            "name": "cerebras_claude_controller",
            "description": "Cerebras bulk + Claude for controller - smart question selection",
            "cfg": {
                "providers": {"cerebras": {"base_url": "https://api.cerebras.ai/v1"}},
                "models": {
                    "interviewer": {"name": "cerebras:llama-3.3-70b"},
                    "ranker": {
                        "name": "cerebras:llama-3.3-70b",
                        "branch_classifier": {"name": "cerebras:llama3.1-8b"},
                        "profile": {"name": "cerebras:llama-3.3-70b"},
                        "themes": {"name": "cerebras:llama-3.3-70b"},
                        "teaching_candidates": {"name": "cerebras:llama-3.3-70b"},
                        "controller": {"name": "anthropic:claude-sonnet-4-20250514"},
                        "readiness": {"name": "cerebras:llama-3.3-70b"},
                    },
                },
                "conversation": {"max_turns": 8, "min_turns_before_commit": 5},
            },
        },
        
        # === HYBRID: CEREBRAS + CLAUDE FOR TEACHING CANDIDATES ===
        {
            "name": "cerebras_claude_teaching",
            "description": "Cerebras bulk + Claude for teaching candidate extraction",
            "cfg": {
                "providers": {"cerebras": {"base_url": "https://api.cerebras.ai/v1"}},
                "models": {
                    "interviewer": {"name": "cerebras:llama-3.3-70b"},
                    "ranker": {
                        "name": "cerebras:llama-3.3-70b",
                        "branch_classifier": {"name": "cerebras:llama3.1-8b"},
                        "profile": {"name": "cerebras:llama-3.3-70b"},
                        "themes": {"name": "cerebras:llama-3.3-70b"},
                        "teaching_candidates": {"name": "anthropic:claude-sonnet-4-20250514"},
                        "controller": {"name": "cerebras:llama-3.3-70b"},
                        "readiness": {"name": "cerebras:llama-3.3-70b"},
                    },
                },
                "conversation": {"max_turns": 8, "min_turns_before_commit": 5},
            },
        },
        
        # === ALL OPENAI (GPT-4O-MINI for speed) ===
        {
            "name": "all_gpt4o_mini",
            "description": "All GPT-4o-mini - OpenAI's fast/cheap option",
            "cfg": {
                "models": {
                    "interviewer": {"name": "openai:gpt-4o-mini"},
                    "ranker": {
                        "name": "openai:gpt-4o-mini",
                        "branch_classifier": {"name": "openai:gpt-4o-mini"},
                        "profile": {"name": "openai:gpt-4o-mini"},
                        "themes": {"name": "openai:gpt-4o-mini"},
                        "teaching_candidates": {"name": "openai:gpt-4o-mini"},
                        "controller": {"name": "openai:gpt-4o-mini"},
                        "readiness": {"name": "openai:gpt-4o-mini"},
                    },
                },
                "conversation": {"max_turns": 8, "min_turns_before_commit": 5},
            },
        },
        
        # === HYBRID: GPT-4O-MINI INTERVIEWER + CEREBRAS RANKER ===
        {
            "name": "gpt4o_mini_interviewer_cerebras_ranker",
            "description": "GPT-4o-mini interviewer + Cerebras ranker - quality questions, fast analysis",
            "cfg": {
                "providers": {"cerebras": {"base_url": "https://api.cerebras.ai/v1"}},
                "models": {
                    "interviewer": {"name": "openai:gpt-4o-mini"},
                    "ranker": {
                        "name": "cerebras:llama-3.3-70b",
                        "branch_classifier": {"name": "cerebras:llama3.1-8b"},
                        "profile": {"name": "cerebras:llama-3.3-70b"},
                        "themes": {"name": "cerebras:llama-3.3-70b"},
                        "teaching_candidates": {"name": "cerebras:llama-3.3-70b"},
                        "controller": {"name": "cerebras:llama-3.3-70b"},
                        "readiness": {"name": "cerebras:llama-3.3-70b"},
                    },
                },
                "conversation": {"max_turns": 8, "min_turns_before_commit": 5},
            },
        },
        
        # === ALL ANTHROPIC (QUALITY BASELINE) ===
        {
            "name": "all_claude_sonnet",
            "description": "All Claude Sonnet - quality baseline",
            "cfg": {
                "models": {
                    "interviewer": {"name": "anthropic:claude-sonnet-4-20250514"},
                    "ranker": {
                        "name": "anthropic:claude-sonnet-4-20250514",
                        "branch_classifier": {"name": "anthropic:claude-3-5-haiku-20241022"},
                        "profile": {"name": "anthropic:claude-sonnet-4-20250514"},
                        "themes": {"name": "anthropic:claude-sonnet-4-20250514"},
                        "teaching_candidates": {"name": "anthropic:claude-sonnet-4-20250514"},
                        "controller": {"name": "anthropic:claude-sonnet-4-20250514"},
                        "readiness": {"name": "anthropic:claude-sonnet-4-20250514"},
                    },
                },
                "conversation": {"max_turns": 8, "min_turns_before_commit": 5},
            },
        },
        
        # === ANTHROPIC HAIKU (FAST + CHEAP) ===
        {
            "name": "all_claude_haiku",
            "description": "All Claude Haiku - Anthropic's fast/cheap option",
            "cfg": {
                "models": {
                    "interviewer": {"name": "anthropic:claude-3-5-haiku-20241022"},
                    "ranker": {
                        "name": "anthropic:claude-3-5-haiku-20241022",
                        "branch_classifier": {"name": "anthropic:claude-3-5-haiku-20241022"},
                        "profile": {"name": "anthropic:claude-3-5-haiku-20241022"},
                        "themes": {"name": "anthropic:claude-3-5-haiku-20241022"},
                        "teaching_candidates": {"name": "anthropic:claude-3-5-haiku-20241022"},
                        "controller": {"name": "anthropic:claude-3-5-haiku-20241022"},
                        "readiness": {"name": "anthropic:claude-3-5-haiku-20241022"},
                    },
                },
                "conversation": {"max_turns": 8, "min_turns_before_commit": 5},
            },
        },
    ]


# ============================================================================
# Rate Limit Detection
# ============================================================================

RATE_LIMIT_PATTERNS = [
    r"rate.?limit",
    r"429",
    r"too many requests",
    r"quota",
    r"exceeded",
    r"insufficient.?credits",
    r"billing",
    r"credit.?limit",
    r"usage.?limit",
]


def is_rate_limit_error(error: Exception) -> tuple[bool, Optional[str]]:
    """
    Detect if an error is a rate limit / quota error.
    Returns (is_rate_limit, provider_name).
    """
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()
    
    # Check for rate limit patterns
    is_rate_limit = any(re.search(p, error_str) for p in RATE_LIMIT_PATTERNS)
    is_rate_limit = is_rate_limit or any(re.search(p, error_type) for p in RATE_LIMIT_PATTERNS)
    
    if not is_rate_limit:
        return False, None
    
    # Try to identify provider
    provider = None
    if "anthropic" in error_str or "claude" in error_str:
        provider = "anthropic"
    elif "openai" in error_str or "gpt" in error_str:
        provider = "openai"
    elif "cerebras" in error_str or "llama" in error_str:
        provider = "cerebras"
    
    return True, provider


def get_providers_in_config(cfg: Dict[str, Any]) -> Set[str]:
    """Extract all providers used in a routing config."""
    providers = set()
    models = cfg.get("cfg", {}).get("models", {})
    
    def extract_provider(model_str: str) -> Optional[str]:
        if ":" in model_str:
            return model_str.split(":")[0]
        # Default providers by model name
        if "claude" in model_str.lower():
            return "anthropic"
        if "gpt" in model_str.lower():
            return "openai"
        if "llama" in model_str.lower():
            return "cerebras"
        return None
    
    # Interviewer
    if "interviewer" in models:
        p = extract_provider(models["interviewer"].get("name", ""))
        if p:
            providers.add(p)
    
    # Ranker and sub-tasks
    ranker = models.get("ranker", {})
    if isinstance(ranker, dict):
        for key, val in ranker.items():
            if isinstance(val, dict) and "name" in val:
                p = extract_provider(val["name"])
                if p:
                    providers.add(p)
            elif isinstance(val, str):
                p = extract_provider(val)
                if p:
                    providers.add(p)
    
    return providers


# ============================================================================
# User Simulation
# ============================================================================

def simulate_user_reply(
    llm: LLMClient,
    user_model: str,
    persona: Persona,
    transcript: List[Dict[str, str]],
    temperature: float = 0.7,
) -> str:
    """Simulate a user answering the assistant's most recent question."""
    system = (
        "You are a user trying a demo of someone's conversational app.\n"
        "Answer naturally and honestly as *yourself*.\n"
        "Do not mention that you are simulated.\n"
        "Keep your answer to 1–3 sentences.\n\n"
        "Here are some things about you:\n"
        f"{persona.background}\n"
    )

    convo = "\n".join([f"{m['role'].capitalize()}: {m['content']}" for m in transcript[-12:]])
    user_prompt = (
        "Conversation so far:\n"
        f"{convo}\n\n"
        "Now respond as the user to the assistant's latest message."
    )

    return llm.chat(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        model=user_model,
        temperature=temperature,
        max_tokens=220,
    ).strip()


# ============================================================================
# Single Run
# ============================================================================

def write_config_file(cfg: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def run_single_benchmark(
    persona: Persona,
    routing: Dict[str, Any],
    user_model: str,
    out_dir: Path,
    session: BenchmarkSession,
) -> BenchmarkResult:
    """Run a single benchmark, handling errors gracefully."""
    
    run_id = str(uuid.uuid4())[:8]
    result = BenchmarkResult(
        persona=persona.name,
        routing=routing["name"],
        user_model=user_model,
        status="pending",
    )
    
    start_time = time.time()
    
    try:
        # Setup config
        cfg_path = out_dir / f"routing_{routing['name']}_{run_id}.yaml"
        write_config_file(routing["cfg"], cfg_path)
        
        os.environ["LIMINAL_CONFIG_PATH"] = str(cfg_path)
        reset_app_config_cache()
        
        # Separate DB per run
        db_path = out_dir / f"bench_{persona.name}_{routing['name']}_{run_id}.db"
        orch = DiscoveryOrchestrator(
            user_id=f"bench_{persona.name}_{run_id}",
            db_path=str(db_path)
        )
        
        llm = LLMClient()
        
        transcript: List[Dict[str, str]] = []
        timings: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        
        # Start conversation
        assistant_msg = orch.start()
        transcript.append({"role": "assistant", "content": assistant_msg})
        
        max_turns = int(routing["cfg"].get("conversation", {}).get("max_turns", 8))
        
        for turn_idx in range(max_turns):
            # User simulation
            t0 = time.time()
            try:
                user_msg = simulate_user_reply(
                    llm, user_model=user_model,
                    persona=persona, transcript=transcript
                )
                t1 = time.time()
            except Exception as e:
                is_rate_limit, provider = is_rate_limit_error(e)
                if is_rate_limit:
                    result.status = "rate_limit"
                    result.error_message = str(e)
                    result.error_provider = provider or "user_model"
                    result.turns_completed = turn_idx
                    if provider:
                        session.blocked_providers.add(provider)
                    return result
                raise
            
            transcript.append({"role": "user", "content": user_msg})
            
            # Orchestrator response
            o0 = time.time()
            try:
                assistant_msg = orch.process_user_message(user_msg)
                o1 = time.time()
            except Exception as e:
                is_rate_limit, provider = is_rate_limit_error(e)
                if is_rate_limit:
                    result.status = "rate_limit"
                    result.error_message = str(e)
                    result.error_provider = provider
                    result.turns_completed = turn_idx + 1
                    if provider:
                        session.blocked_providers.add(provider)
                    return result
                raise
            
            transcript.append({"role": "assistant", "content": assistant_msg})
            
            timings.append({
                "turn": turn_idx + 1,
                "user_sim_time_s": t1 - t0,
                "orchestrator_time_s": o1 - o0,
            })
            
            result.turns_completed = turn_idx + 1
            
            # Check if teaching phase reached
            if (hasattr(orch.schema, "teaching_recommendation") and 
                orch.schema.teaching_recommendation and 
                orch.schema.teaching_recommendation.ready):
                result.reached_teaching = True
                result.final_topic = orch.schema.teaching_recommendation.target_topic
                break
        
        # Success - save artifact
        artifact = {
            "run_id": run_id,
            "persona": persona.name,
            "routing": routing["name"],
            "routing_description": routing.get("description", ""),
            "user_model": user_model,
            "config_path": str(cfg_path),
            "db_path": str(db_path),
            "timings": timings,
            "transcript": transcript,
            "errors": errors,
            "final_schema": orch.get_schema(),
            "reached_teaching": result.reached_teaching,
            "final_topic": result.final_topic,
        }
        
        out_path = out_dir / f"persona_run_{persona.name}__{routing['name']}__{run_id}.json"
        out_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        
        result.status = "success"
        result.artifact_path = str(out_path)
        result.total_time_s = time.time() - start_time
        
        # Create transcript preview
        if transcript:
            preview_lines = []
            for msg in transcript[-4:]:
                role = msg["role"].upper()
                content = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
                preview_lines.append(f"{role}: {content}")
            result.transcript_preview = "\n".join(preview_lines)
        
    except Exception as e:
        result.status = "error"
        result.error_message = f"{type(e).__name__}: {str(e)}"
        result.total_time_s = time.time() - start_time
        
        # Check if it's a rate limit error we didn't catch
        is_rate_limit, provider = is_rate_limit_error(e)
        if is_rate_limit:
            result.status = "rate_limit"
            result.error_provider = provider
            if provider:
                session.blocked_providers.add(provider)
    
    return result


# ============================================================================
# Summary Report
# ============================================================================

def generate_summary(session: BenchmarkSession, out_dir: Path) -> str:
    """Generate a markdown summary of the benchmark results."""
    lines = [
        "# Benchmark Results Summary",
        "",
        f"**Run Date:** {session.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Total Runs:** {len(session.results)}",
        "",
    ]
    
    # Summary stats
    success = [r for r in session.results if r.status == "success"]
    rate_limits = [r for r in session.results if r.status == "rate_limit"]
    errors = [r for r in session.results if r.status == "error"]
    reached_teaching = [r for r in success if r.reached_teaching]
    
    lines.extend([
        "## Summary Stats",
        "",
        f"- ✅ **Successful:** {len(success)}",
        f"- 🎯 **Reached Teaching Phase:** {len(reached_teaching)}",
        f"- ⚠️ **Rate Limited:** {len(rate_limits)}",
        f"- ❌ **Errors:** {len(errors)}",
        "",
    ])
    
    # Blocked providers
    if session.blocked_providers:
        lines.extend([
            "## Blocked Providers (Hit Rate Limits)",
            "",
        ])
        for provider in sorted(session.blocked_providers):
            lines.append(f"- 🚫 **{provider}**")
        lines.append("")
    
    # Results by routing config
    lines.extend([
        "## Results by Routing Config",
        "",
    ])
    
    routings = {}
    for r in session.results:
        if r.routing not in routings:
            routings[r.routing] = []
        routings[r.routing].append(r)
    
    for routing_name, results in sorted(routings.items()):
        success_count = len([r for r in results if r.status == "success"])
        teaching_count = len([r for r in results if r.reached_teaching])
        avg_time = sum(r.total_time_s for r in results if r.status == "success") / max(1, success_count)
        avg_turns = sum(r.turns_completed for r in results if r.status == "success") / max(1, success_count)
        
        status_emoji = "✅" if success_count == len(results) else "⚠️" if success_count > 0 else "❌"
        
        lines.extend([
            f"### {status_emoji} {routing_name}",
            "",
            f"- Runs: {success_count}/{len(results)} successful",
            f"- Reached Teaching: {teaching_count}/{success_count}" if success_count > 0 else "- Reached Teaching: N/A",
            f"- Avg Time: {avg_time:.1f}s" if success_count > 0 else "- Avg Time: N/A",
            f"- Avg Turns: {avg_turns:.1f}" if success_count > 0 else "- Avg Turns: N/A",
            "",
        ])
        
        for r in results:
            if r.status == "success":
                topic_str = f" → **{r.final_topic}**" if r.final_topic else ""
                lines.append(f"  - ✅ {r.persona}: {r.turns_completed} turns, {r.total_time_s:.1f}s{topic_str}")
            elif r.status == "rate_limit":
                lines.append(f"  - ⚠️ {r.persona}: Rate limited ({r.error_provider})")
            else:
                lines.append(f"  - ❌ {r.persona}: {r.error_message[:50]}...")
        
        lines.append("")
    
    # Detailed results table
    lines.extend([
        "## Detailed Results",
        "",
        "| Persona | Routing | Status | Turns | Time | Teaching | Topic |",
        "|---------|---------|--------|-------|------|----------|-------|",
    ])
    
    for r in session.results:
        status = "✅" if r.status == "success" else "⚠️" if r.status == "rate_limit" else "❌"
        teaching = "✅" if r.reached_teaching else "❌"
        topic = r.final_topic[:30] + "..." if r.final_topic and len(r.final_topic) > 30 else (r.final_topic or "-")
        lines.append(
            f"| {r.persona} | {r.routing} | {status} {r.status} | {r.turns_completed} | {r.total_time_s:.1f}s | {teaching} | {topic} |"
        )
    
    lines.extend([
        "",
        "## Recommendations",
        "",
    ])
    
    # Generate recommendations
    if reached_teaching:
        # Find fastest successful config that reached teaching
        teaching_results = [r for r in success if r.reached_teaching]
        if teaching_results:
            fastest = min(teaching_results, key=lambda r: r.total_time_s)
            lines.append(f"- **Fastest to Teaching:** `{fastest.routing}` ({fastest.total_time_s:.1f}s, {fastest.turns_completed} turns)")
        
        # Find config with most consistent teaching success
        routing_teaching_rates = {}
        for r in success:
            if r.routing not in routing_teaching_rates:
                routing_teaching_rates[r.routing] = {"success": 0, "total": 0}
            routing_teaching_rates[r.routing]["total"] += 1
            if r.reached_teaching:
                routing_teaching_rates[r.routing]["success"] += 1
        
        best_rate_routing = max(
            routing_teaching_rates.keys(),
            key=lambda k: routing_teaching_rates[k]["success"] / max(1, routing_teaching_rates[k]["total"])
        )
        rate = routing_teaching_rates[best_rate_routing]
        lines.append(f"- **Most Reliable:** `{best_rate_routing}` ({rate['success']}/{rate['total']} reached teaching)")
    
    if session.blocked_providers:
        lines.append(f"- **Avoid:** {', '.join(session.blocked_providers)} (hit rate limits)")
    
    lines.append("")
    
    return "\n".join(lines)


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Safe benchmark runner with rate limit handling")
    parser.add_argument(
        "--user-model",
        default="cerebras:llama-3.3-70b",
        help="Model for user simulation (kept constant across all runs)",
    )
    parser.add_argument("--out-dir", default=str(RESULTS_DIR))
    parser.add_argument("--personas", nargs="*", default=None, help="Specific personas to run")
    parser.add_argument("--routings", nargs="*", default=None, help="Specific routings to run")
    parser.add_argument("--skip-blocked", action="store_true", help="Skip configs using blocked providers")
    args = parser.parse_args()
    
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize session
    session = BenchmarkSession()
    
    # Get personas and routings
    personas = PERSONAS
    if args.personas:
        wanted = set(args.personas)
        personas = [p for p in personas if p.name in wanted]
    
    routings = build_routing_configs()
    if args.routings:
        wanted = set(args.routings)
        routings = [r for r in routings if r["name"] in wanted]
    
    print(f"=" * 60)
    print(f"BENCHMARK SESSION")
    print(f"=" * 60)
    print(f"User Model: {args.user_model}")
    print(f"Personas: {[p.name for p in personas]}")
    print(f"Routings: {[r['name'] for r in routings]}")
    print(f"Output Dir: {out_dir}")
    print(f"=" * 60)
    print()
    
    total_runs = len(personas) * len(routings)
    run_count = 0
    
    for persona in personas:
        for routing in routings:
            run_count += 1
            
            # Check if we should skip due to blocked providers
            config_providers = get_providers_in_config(routing)
            blocked_in_config = config_providers & session.blocked_providers
            
            # Also check user model provider
            user_provider = args.user_model.split(":")[0] if ":" in args.user_model else None
            if user_provider and user_provider in session.blocked_providers:
                blocked_in_config.add(user_provider)
            
            if args.skip_blocked and blocked_in_config:
                print(f"[{run_count}/{total_runs}] SKIPPING {persona.name} x {routing['name']}")
                print(f"         Blocked providers in config: {blocked_in_config}")
                print()
                continue
            
            print(f"[{run_count}/{total_runs}] Running {persona.name} x {routing['name']}...")
            print(f"         Description: {routing.get('description', 'N/A')}")
            
            result = run_single_benchmark(
                persona=persona,
                routing=routing,
                user_model=args.user_model,
                out_dir=out_dir,
                session=session,
            )
            
            session.results.append(result)
            
            # Print result
            if result.status == "success":
                topic_str = f" → {result.final_topic}" if result.final_topic else ""
                print(f"         ✅ SUCCESS: {result.turns_completed} turns, {result.total_time_s:.1f}s{topic_str}")
            elif result.status == "rate_limit":
                print(f"         ⚠️ RATE LIMITED: {result.error_provider}")
                print(f"         Message: {result.error_message[:100]}...")
            else:
                print(f"         ❌ ERROR: {result.error_message[:100]}...")
            
            print()
            
            # If user model hit rate limit, we can't continue at all
            if result.status == "rate_limit" and result.error_provider == "user_model":
                print("=" * 60)
                print("STOPPING: User model hit rate limit - cannot continue")
                print("=" * 60)
                break
        
        # Break outer loop too
        if session.results and session.results[-1].status == "rate_limit":
            last_result = session.results[-1]
            if last_result.error_provider == "user_model":
                break
    
    # Generate summary
    print("=" * 60)
    print("GENERATING SUMMARY")
    print("=" * 60)
    
    summary = generate_summary(session, out_dir)
    summary_path = out_dir / "BENCHMARK_SUMMARY.md"
    summary_path.write_text(summary, encoding="utf-8")
    print(f"Summary saved to: {summary_path}")
    
    # Save raw results JSON
    results_json = {
        "start_time": session.start_time.isoformat(),
        "user_model": args.user_model,
        "blocked_providers": list(session.blocked_providers),
        "results": [
            {
                "persona": r.persona,
                "routing": r.routing,
                "status": r.status,
                "error_message": r.error_message,
                "error_provider": r.error_provider,
                "turns_completed": r.turns_completed,
                "total_time_s": r.total_time_s,
                "reached_teaching": r.reached_teaching,
                "final_topic": r.final_topic,
                "artifact_path": r.artifact_path,
            }
            for r in session.results
        ],
    }
    results_json_path = out_dir / "benchmark_results.json"
    results_json_path.write_text(json.dumps(results_json, indent=2), encoding="utf-8")
    print(f"Results JSON saved to: {results_json_path}")
    
    # Print summary to console
    print()
    print(summary)


if __name__ == "__main__":
    main()

