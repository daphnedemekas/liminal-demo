#!/usr/bin/env python3
"""
Phase-1 microbenchmarks for *this repo's actual tasks*.

This script tests models across the key call sites:
- branch condition classification (string label)
- ranker: update_user_profile (JSON -> UserProfile)
- ranker: update_conversational_themes (JSON -> [ConversationalTheme])
- ranker: update_teaching_candidates (JSON -> [TeachingCandidate])
- ranker: generate_next_question/controller (JSON -> Controller)
- interviewer: generate_next_question (text + constraint checks)

It intentionally avoids "full combinatorial routing sweeps". Use results to
pick top 1–2 models per call site, then do a small factorial sweep.
"""

from __future__ import annotations

import argparse
import json
import time
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.interviewer import InterviewerAgent
from src.agents.goal_discovery_ranker import GoalDiscoveryRanker
from src.llm_client import LLMClient
from src.prompt_loader import PromptLoader
from src.schema.full_schema import (
    Controller,
    ConversationalTheme,
    DiscoverySchema,
    InterviewState,
    TeachingCandidate,
    UserProfile,
)


RESULTS_DIR = Path(__file__).parent / "results"


# ----------------------------
# Scenarios
# ----------------------------

SCENARIOS: Dict[str, List[Dict[str, str]]] = {
    # Concrete topic + explicit gap
    "backprop_gap": [
        {"role": "assistant", "content": "When you encounter something you don't understand, does it feel more like an invitation or an itch?"},
        {"role": "user", "content": "It feels like an itch. If I don't understand something, it nags at me until I resolve it."},
        {"role": "assistant", "content": "What kinds of things tend to create that itch for you?"},
        {"role": "user", "content": "Neural networks. Deep learning feels like black magic."},
        {"role": "assistant", "content": "What about it feels like black magic?"},
        {"role": "user", "content": "Forward pass makes sense, but backpropagation doesn't. How does the error actually propagate backward?"},
    ],
    # Vague + preferences; should pivot to a concrete confusion moment
    "preference_heavy": [
        {"role": "assistant", "content": "What have you been curious about lately?"},
        {"role": "user", "content": "I just want to understand things deeply. Surface explanations frustrate me."},
        {"role": "assistant", "content": "Got it. Do you like to zoom into details or stay on the big picture?"},
        {"role": "user", "content": "Zoom in. I want the mechanism. Also I hate when people paraphrase me."},
        {"role": "assistant", "content": "Okay."},
        {"role": "user", "content": "Also I don't want to be asked to pick a topic upfront."},
    ],
    # Personal context (should bridge)
    "personal_context": [
        {"role": "assistant", "content": "What have you been curious about lately?"},
        {"role": "user", "content": "I feel stuck at work. I keep noticing I can't explain my decisions clearly."},
        {"role": "assistant", "content": "When does that happen most?"},
        {"role": "user", "content": "When I have to justify tradeoffs in product decisions. I can feel the reasons but can't articulate them."},
    ],
}


# ----------------------------
# Helpers / checks
# ----------------------------


def _as_conversation_text(history: List[Dict[str, str]]) -> str:
    return "\n".join([f"{m['role'].capitalize()}: {m['content']}" for m in history])


def _is_one_question(text: str) -> bool:
    # heuristic: allow "?" exactly once
    return text.count("?") == 1


def _violates_no_topic_asking(text: str) -> bool:
    t = text.lower()
    banned = [
        "what topic",
        "what are you interested in",
        "what are you curious about",
        "what have you been drawn to",
        "what do you want to learn about",
        "pick a topic",
        "choose a topic",
        "name a topic",
    ]
    return any(b in t for b in banned)


def _violates_no_paraphrase_echo(text: str) -> bool:
    t = text.lower()
    banned_starts = [
        "so what you're saying",
        "it sounds like",
        "so it's like",
        "what you're saying is",
    ]
    return any(b in t for b in banned_starts)


def _basic_interviewer_checks(text: str) -> Dict[str, Any]:
    return {
        "one_question": _is_one_question(text),
        "violates_no_topic_asking": _violates_no_topic_asking(text),
        "violates_no_paraphrase_echo": _violates_no_paraphrase_echo(text),
        "chars": len(text),
    }


def _validate_list_of_models(items: Any, model_cls) -> Tuple[bool, Optional[str], Optional[int]]:
    try:
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            return False, "not a list/dict", None
        parsed = []
        for x in items:
            # Mirror production behavior: allow models to emit nulls for fields that have defaults.
            if isinstance(x, dict):
                x = {k: v for k, v in x.items() if v is not None}
            parsed.append(model_cls(**x))
        return True, None, len(parsed)
    except Exception as e:
        return False, str(e), None


def _safe_json(obj: Any) -> Any:
    try:
        json.dumps(obj)
        return obj
    except Exception:
        return str(obj)


# ----------------------------
# Task runners
# ----------------------------


@dataclass
class TaskResult:
    task: str
    scenario: str
    model: str
    success: bool
    duration_s: float
    meta: Dict[str, Any]


def run_branch_classifier(llm: LLMClient, model: str, scenario: str, history: List[Dict[str, str]]) -> TaskResult:
    user_message = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
    prompt = f"""Classify the user's most recent response into ONE of these categories:

- topic_mentioned
- personal_shared
- deflection
- preference_signal
- question_asked
- unclear

Recent conversation:
{_as_conversation_text(history[-3:] if len(history) > 3 else history)}

User's most recent response: "{user_message}"

Respond with ONLY the category name, nothing else."""

    start = time.time()
    try:
        out = llm.chat([{"role": "user", "content": prompt}], model=model, temperature=0.2, max_tokens=20).strip().lower()
        valid = {"topic_mentioned", "personal_shared", "deflection", "preference_signal", "question_asked", "unclear"}
        ok = out in valid
        return TaskResult("branch_classifier", scenario, model, ok, time.time() - start, {"output": out})
    except Exception as e:
        return TaskResult("branch_classifier", scenario, model, False, time.time() - start, {"error": str(e)})


def _make_min_schema(session_id: str = "bench") -> DiscoverySchema:
    return DiscoverySchema(
        session_id=session_id,
        user_profile=UserProfile(),
        conversational_themes=[],
        teaching_candidates=[],
        topic_candidates=[],
        interview_state=InterviewState(),
        controller=Controller(
            next_action="general_explore",
            next_question="",
            question_intent="probe_dimensions",
            fallback_questions=[],
            branch_condition="unclear",
        ),
    )


def run_ranker_profile(llm: LLMClient, model: str, scenario: str, history: List[Dict[str, str]], loader: PromptLoader) -> TaskResult:
    schema = _make_min_schema(f"bench_{scenario}")
    prompt = loader.load_ranker_prompt("update_user_profile").format(
        current_profile=schema.user_profile.model_dump(),
        conversation=_as_conversation_text(history),
    )
    start = time.time()
    try:
        out = llm.chat_with_json(
            [{"role": "user", "content": prompt}],
            model=model,
            temperature=0.3,
            max_tokens=1200,
            json_top_level="object",
        )
        # validate shape by constructing UserProfile (fields nested)
        UserProfile(**out)
        return TaskResult("ranker_profile", scenario, model, True, time.time() - start, {"keys": list(out.keys())[:15]})
    except Exception as e:
        return TaskResult("ranker_profile", scenario, model, False, time.time() - start, {"error": str(e)})


def run_ranker_themes(llm: LLMClient, model: str, scenario: str, history: List[Dict[str, str]], loader: PromptLoader) -> TaskResult:
    schema = _make_min_schema(f"bench_{scenario}")
    prompt = loader.load_ranker_prompt("update_conversational_themes").format(
        conversational_themes=[t.model_dump() for t in schema.conversational_themes],
        conversation=_as_conversation_text(history),
    )
    start = time.time()
    try:
        out = llm.chat_with_json(
            [{"role": "user", "content": prompt}],
            model=model,
            temperature=0.1,
            max_tokens=1500,
            json_top_level="array",
        )
        ok, err, n = _validate_list_of_models(out, ConversationalTheme)
        return TaskResult("ranker_themes", scenario, model, ok, time.time() - start, {"n": n, "error": err})
    except Exception as e:
        return TaskResult("ranker_themes", scenario, model, False, time.time() - start, {"error": str(e)})


def run_ranker_teaching_candidates(llm: LLMClient, model: str, scenario: str, history: List[Dict[str, str]], loader: PromptLoader) -> TaskResult:
    schema = _make_min_schema(f"bench_{scenario}")
    prompt = loader.load_ranker_prompt("update_teaching_candidates").format(
        teaching_candidates=[t.model_dump() for t in schema.teaching_candidates],
        conversational_themes=[t.model_dump() for t in schema.conversational_themes],
        conversation=_as_conversation_text(history),
    )
    start = time.time()
    try:
        out = llm.chat_with_json(
            [{"role": "user", "content": prompt}],
            model=model,
            temperature=0.3,
            max_tokens=1500,
            json_top_level="array",
        )
        ok, err, n = _validate_list_of_models(out, TeachingCandidate)
        return TaskResult("ranker_teaching_candidates", scenario, model, ok, time.time() - start, {"n": n, "error": err})
    except Exception as e:
        return TaskResult("ranker_teaching_candidates", scenario, model, False, time.time() - start, {"error": str(e)})


def run_ranker_controller(llm: LLMClient, model: str, scenario: str, history: List[Dict[str, str]]) -> TaskResult:
    # Use GoalDiscoveryRanker's schema dump helper (adds derived.urgency)
    ranker = GoalDiscoveryRanker(llm)
    schema = _make_min_schema(f"bench_{scenario}")
    schema.interview_state.turns_elapsed = max(0, len([m for m in history if m["role"] == "user"]) - 1)
    schema_dump = ranker._schema_dump_for_llm(schema)  # type: ignore[attr-defined]

    # Derive branch_condition from last user message quickly (not part of this benchmark)
    branch_condition = "unclear"
    prompt = ranker.prompt_loader.load_ranker_prompt("generate_next_question").format(
        schema=schema_dump,
        branch_condition=branch_condition,
    )
    start = time.time()
    try:
        out = llm.chat_with_json(
            [{"role": "user", "content": prompt}],
            model=model,
            temperature=0.4,
            max_tokens=700,
            json_top_level="object",
        )
        Controller(**out)
        return TaskResult("ranker_controller", scenario, model, True, time.time() - start, {})
    except Exception as e:
        return TaskResult("ranker_controller", scenario, model, False, time.time() - start, {"error": str(e)})


def run_interviewer_question(llm: LLMClient, model: str, scenario: str, history: List[Dict[str, str]]) -> TaskResult:
    agent = InterviewerAgent(llm)
    schema = _make_min_schema(f"bench_{scenario}")
    # Keep controller suggestion empty; we're testing the base interviewer generation quality.
    system_prompt = agent.prompt_loader.load_interviewer_prompt("general_continuation")
    formatted = agent._format_prompt(system_prompt, agent._build_context(schema))  # type: ignore[attr-defined]

    messages = [{"role": "system", "content": formatted}]
    messages.extend(history)

    start = time.time()
    try:
        out = llm.chat(messages, model=model, temperature=0.7, max_tokens=300).strip()
        checks = _basic_interviewer_checks(out)
        ok = bool(checks["one_question"]) and not checks["violates_no_topic_asking"]
        return TaskResult("interviewer_question", scenario, model, ok, time.time() - start, {"checks": checks, "text": out})
    except Exception as e:
        return TaskResult("interviewer_question", scenario, model, False, time.time() - start, {"error": str(e)})


# ----------------------------
# Main
# ----------------------------


DEFAULT_MODELS = [
    # Cerebras
    "cerebras:llama-3.3-70b",
    "cerebras:llama3.1-8b",
    # OpenAI
    "openai:gpt-4o",
    "openai:gpt-4o-mini",
    # Anthropic
    "anthropic:claude-sonnet-4-20250514",
    "anthropic:claude-3-5-haiku-20241022",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="*", default=None, help="Model list (prefix with provider: ...)")
    parser.add_argument("--scenarios", nargs="*", default=None, help=f"Scenarios to run (default: {list(SCENARIOS.keys())})")
    parser.add_argument("--out", default=str(RESULTS_DIR / "task_benchmarks.json"))
    args = parser.parse_args()

    models = args.models or DEFAULT_MODELS
    scenario_names = args.scenarios or list(SCENARIOS.keys())

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    llm = LLMClient()
    loader = PromptLoader()

    all_results: List[TaskResult] = []
    tasks = [
        run_branch_classifier,
        lambda llm, model, scen, hist: run_ranker_profile(llm, model, scen, hist, loader),
        lambda llm, model, scen, hist: run_ranker_themes(llm, model, scen, hist, loader),
        lambda llm, model, scen, hist: run_ranker_teaching_candidates(llm, model, scen, hist, loader),
        run_ranker_controller,
        run_interviewer_question,
    ]

    for scen in scenario_names:
        history = SCENARIOS[scen]
        for model in models:
            for tfn in tasks:
                r = tfn(llm, model, scen, history)
                all_results.append(r)
                print(f"{r.task:<28} {scen:<18} {model:<38} {'OK' if r.success else 'FAIL'} {r.duration_s:.2f}s")

    # Serialize
    payload = [
        {
            "task": r.task,
            "scenario": r.scenario,
            "model": r.model,
            "success": r.success,
            "duration_s": r.duration_s,
            "meta": _safe_json(r.meta),
        }
        for r in all_results
    ]
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote: {out_path}")


if __name__ == "__main__":
    main()


