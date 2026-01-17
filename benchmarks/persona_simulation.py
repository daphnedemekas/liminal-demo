#!/usr/bin/env python3
"""
End-to-end benchmark: simulate user personas with a fixed user model, and run the
discovery system under different routing configs.

Key constraints (per user request):
- The user simulator prompt MUST NOT mention that the system is identifying a topic.
- The user simulator should just "act like a user doing a demo", answer honestly,
  based on persona background.
- Use the SAME user model across all runs for consistency.

Outputs judge-ready artifacts (JSON) with:
- persona, routing config, user model
- full transcript
- per-turn timings (user_sim_time_s, orchestrator_time_s)
- final schema (if available)
"""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).parent.parent

import sys
sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.orchestrator import DiscoveryOrchestrator
from src.config import reset_app_config_cache
from src.llm_client import LLMClient


RESULTS_DIR = Path(__file__).parent / "results" / "persona_runs"


@dataclass
class Persona:
    name: str
    background: str


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


def _write_config_file(cfg: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # JSON is also valid YAML; keep it simple and deterministic.
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _build_routing_configs() -> List[Dict[str, Any]]:
    """
    A small set of routing configs to compare.
    Keep this small; later we can expand or generate factorial sweeps.
    """
    return [
        {
            "name": "all_cerebras_fast",
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
        {
            "name": "cerebras_with_stronger_interviewer",
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
        {
            "name": "anthropic_quality_baseline",
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
    ]


def simulate_user_reply(
    llm: LLMClient,
    user_model: str,
    persona: Persona,
    transcript: List[Dict[str, str]],
    temperature: float = 0.7,
) -> str:
    """
    Simulate a user answering the assistant's most recent question.
    MUST NOT mention that any topic-identification is happening.
    """
    system = (
        "You are a user trying a demo of someone's conversational app.\n"
        "Answer naturally and honestly as *yourself*.\n"
        "Do not mention that you are simulated.\n"
        "Keep your answer to 1–3 sentences.\n\n"
        "Here are some things about you:\n"
        f"{persona.background}\n"
    )

    # Provide conversation context without revealing any hidden objective.
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


def run_one(persona: Persona, routing: Dict[str, Any], user_model: str, out_dir: Path) -> Path:
    run_id = str(uuid.uuid4())[:8]
    cfg_path = out_dir / f"routing_{routing['name']}_{run_id}.yaml"
    _write_config_file(routing["cfg"], cfg_path)

    os.environ["LIMINAL_CONFIG_PATH"] = str(cfg_path)
    reset_app_config_cache()

    # Separate DB per run to avoid cross-contamination.
    db_path = out_dir / f"bench_{persona.name}_{routing['name']}_{run_id}.db"
    orch = DiscoveryOrchestrator(user_id=f"bench_{persona.name}_{run_id}", db_path=str(db_path))

    llm = LLMClient()  # separate client for user sim (still same env config; user_model controls provider)

    transcript: List[Dict[str, str]] = []
    timings: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    assistant_msg = orch.start()
    transcript.append({"role": "assistant", "content": assistant_msg})

    # Run a fixed number of user turns; orchestrator decides when to transition.
    max_turns = int(routing["cfg"].get("conversation", {}).get("max_turns", 8))

    for turn_idx in range(max_turns):
        t0 = time.time()
        try:
            user_msg = simulate_user_reply(llm, user_model=user_model, persona=persona, transcript=transcript)
            t1 = time.time()
        except Exception as e:
            t1 = time.time()
            errors.append({"stage": "user_sim", "turn": turn_idx + 1, "error": repr(e)})
            break

        transcript.append({"role": "user", "content": user_msg})

        o0 = time.time()
        try:
            assistant_msg = orch.process_user_message(user_msg)
            o1 = time.time()
        except Exception as e:
            o1 = time.time()
            errors.append({"stage": "orchestrator", "turn": turn_idx + 1, "error": repr(e)})
            break

        transcript.append({"role": "assistant", "content": assistant_msg})

        timings.append(
            {
                "turn": turn_idx + 1,
                "user_sim_time_s": t1 - t0,
                "orchestrator_time_s": o1 - o0,
            }
        )

        # If the orchestrator transitioned to teaching, stop early.
        if getattr(orch.schema, "teaching_recommendation", None) and orch.schema.teaching_recommendation.ready:
            break

    artifact = {
        "run_id": run_id,
        "persona": persona.name,
        "routing": routing["name"],
        "user_model": user_model,
        "config_path": str(cfg_path),
        "db_path": str(db_path),
        "timings": timings,
        "transcript": transcript,
        "errors": errors,
        "final_schema": orch.get_schema(),
    }

    out_path = out_dir / f"persona_run_{persona.name}__{routing['name']}__{run_id}.json"
    out_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--user-model",
        default="cerebras:llama-3.3-70b",
        help="Model for user simulation (kept constant across all runs).",
    )
    parser.add_argument("--out-dir", default=str(RESULTS_DIR))
    parser.add_argument("--personas", nargs="*", default=None)
    parser.add_argument("--routings", nargs="*", default=None)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    personas = PERSONAS
    if args.personas:
        wanted = set(args.personas)
        personas = [p for p in personas if p.name in wanted]

    routings = _build_routing_configs()
    if args.routings:
        wanted = set(args.routings)
        routings = [r for r in routings if r["name"] in wanted]

    paths: List[str] = []
    for p in personas:
        for r in routings:
            print(f"Running persona={p.name} routing={r['name']} user_model={args.user_model} ...", flush=True)
            out_path = run_one(p, r, user_model=args.user_model, out_dir=out_dir)
            paths.append(str(out_path))

    index = {
        "user_model": args.user_model,
        "personas": [p.name for p in personas],
        "routings": [r["name"] for r in routings],
        "artifacts": paths,
    }
    (out_dir / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(f"\nWrote {len(paths)} artifacts + index.json to {out_dir}")


if __name__ == "__main__":
    main()


