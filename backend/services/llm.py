"""Configurable LLM client for mediation layer calls.

This is NOT used for the agent executor (which always uses Claude Code CLI).
This is for onboarding, user model inference, planning, etc.

Configure via environment variables:
  LLM_PROVIDER=openai (default) | anthropic
  LLM_MODEL=gpt-4o-mini (default)
  OPENAI_API_KEY=...
  ANTHROPIC_API_KEY=...
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── LLM trace log ────────────────────────────────────────────────────
# Every prompt/response pair is appended to this file for live monitoring.
LLM_TRACE_PATH = os.environ.get("LLM_TRACE_PATH", "data/llm_trace.log")

def _trace(label: str, **kwargs):
    """Append a structured trace entry to the LLM log file."""
    try:
        os.makedirs(os.path.dirname(LLM_TRACE_PATH) or ".", exist_ok=True)
        with open(LLM_TRACE_PATH, "a") as f:
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
            f.write(f"\n{'='*80}\n")
            f.write(f"[{ts}] {label}\n")
            f.write(f"{'='*80}\n")
            for k, v in kwargs.items():
                if isinstance(v, list):
                    f.write(f"── {k} ──\n")
                    for i, item in enumerate(v):
                        role = item.get("role", "?")
                        content = item.get("content", "")
                        f.write(f"  [{role}] {content[:2000]}\n")
                        if len(content) > 2000:
                            f.write(f"  ... ({len(content)} chars total)\n")
                else:
                    val = str(v)
                    f.write(f"── {k} ──\n{val[:3000]}\n")
                    if len(val) > 3000:
                        f.write(f"... ({len(val)} chars total)\n")
    except Exception as e:
        logger.debug(f"Trace write failed: {e}")

_client = None
PROVIDER = os.environ.get("LLM_PROVIDER", "openai")
MODEL = os.environ.get("LLM_MODEL", "gpt-5")
MODEL_MINI = os.environ.get("LLM_MODEL_MINI", "gpt-4o-mini")

# Models that require max_completion_tokens instead of max_tokens
_COMPLETION_TOKENS_MODELS = {"gpt-5", "gpt-5-mini", "o1", "o1-mini", "o1-preview", "o3", "o3-mini"}


def _token_limit_kwargs(model: str, limit: int = 2048) -> dict:
    """Return the correct token limit kwarg for the given model."""
    if any(model.startswith(prefix) for prefix in _COMPLETION_TOKENS_MODELS):
        return {"max_completion_tokens": limit}
    return {"max_tokens": limit}


def _get_client():
    global _client
    if _client is not None:
        return _client

    if PROVIDER == "anthropic":
        from anthropic import Anthropic
        _client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    else:
        from openai import OpenAI
        _client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    return _client


def chat(prompt: str, model: Optional[str] = None) -> str:
    """Single-turn LLM call. Returns the text response. Retries once on empty response."""
    client = _get_client()
    m = model or MODEL

    for attempt in range(2):
        _trace("chat()", model=m, prompt=prompt if attempt == 0 else "(retry)")
        t0 = time.time()

        if PROVIDER == "anthropic":
            response = client.messages.create(
                model=m,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            result = response.content[0].text
        else:
            response = client.chat.completions.create(
                model=m,
                messages=[{"role": "user", "content": prompt}],
                **_token_limit_kwargs(m),
            )
            result = response.choices[0].message.content or ""

        _trace("chat() response", model=m, elapsed=f"{time.time()-t0:.1f}s", response=result)

        if result.strip():
            return result
        logger.warning(f"chat() got empty response from {m} (attempt {attempt+1})")

    return result


def chat_messages(system_prompt: str, messages: list[dict], model: Optional[str] = None, json_mode: bool = False) -> str:
    """Multi-turn LLM call. messages is a list of {role, content} dicts. Retries with fallback on empty."""
    client = _get_client()
    m = model or (MODEL_JSON if json_mode else MODEL)

    for attempt in range(3):
        # On third attempt, fall back to a more reliable model
        use_model = m if attempt < 2 else MODEL_MINI
        _trace("chat_messages()", model=use_model, json_mode=str(json_mode),
               system_prompt=system_prompt if attempt == 0 else f"(retry {attempt+1})",
               messages=messages if attempt == 0 else f"(retry {attempt+1})")
        t0 = time.time()

        try:
            if PROVIDER == "anthropic":
                response = client.messages.create(
                    model=use_model,
                    max_tokens=2048,
                    system=system_prompt,
                    messages=messages,
                )
                result = response.content[0].text
                finish = getattr(response, "stop_reason", "unknown")
            else:
                all_messages = [{"role": "system", "content": system_prompt}] + messages
                kwargs = dict(model=use_model, messages=all_messages, **_token_limit_kwargs(use_model))
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                response = client.chat.completions.create(**kwargs)
                result = response.choices[0].message.content or ""
                finish = response.choices[0].finish_reason or "unknown"

            _trace("chat_messages() response", model=use_model, elapsed=f"{time.time()-t0:.1f}s",
                   finish_reason=finish, response=result)

            if result.strip():
                return result
            logger.warning(f"chat_messages() empty from {use_model} (attempt {attempt+1}, finish={finish})")
        except Exception as e:
            logger.warning(f"chat_messages() error on attempt {attempt+1}: {e}")
            result = ""

        if attempt < 2:
            time.sleep(0.5)

    return result


MODEL_JSON = os.environ.get("LLM_MODEL_JSON", "gpt-4o")


def chat_json(prompt: str, model: Optional[str] = None, retries: int = 1):
    """Single-turn LLM call that parses the response as JSON.

    Uses gpt-4o by default (reliable JSON mode support). Override with model param.
    """
    m = model or MODEL_JSON
    last_err = None
    for attempt in range(1 + retries):
        text = _chat_json_mode(prompt, model=m)
        try:
            return parse_json(text)
        except (json.JSONDecodeError, ValueError) as e:
            last_err = e
            if attempt < retries:
                logger.warning(f"chat_json attempt {attempt+1} failed (bad JSON), retrying. Raw: {text[:200]!r}")
                continue
            raise last_err


def _chat_json_mode(prompt: str, model: Optional[str] = None) -> str:
    """Single-turn LLM call with JSON response format enabled."""
    client = _get_client()
    m = model or MODEL
    _trace("_chat_json_mode()", model=m, prompt=prompt)
    t0 = time.time()

    if PROVIDER == "anthropic":
        response = client.messages.create(
            model=m,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        result = response.content[0].text
    else:
        response = client.chat.completions.create(
            model=m,
            messages=[
                {"role": "system", "content": "Respond with valid JSON only. No markdown, no explanation."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            **_token_limit_kwargs(m),
        )
        result = response.choices[0].message.content or ""

    _trace("_chat_json_mode() response", model=m, elapsed=f"{time.time()-t0:.1f}s", response=result)
    return result


def chat_json_parallel(prompts: dict[str, str], model: Optional[str] = None) -> dict[str, dict]:
    """Run multiple chat_json calls concurrently. Returns {key: parsed_json}.

    prompts: dict of {label: prompt_text}
    Failures for individual calls are logged and returned as empty dicts.
    """
    import concurrent.futures

    results = {}

    def _call(key: str, prompt: str):
        try:
            return key, chat_json(prompt, model=model)
        except Exception as e:
            logger.warning(f"Parallel call '{key}' failed: {e}")
            return key, {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(prompts)) as executor:
        futures = [executor.submit(_call, k, p) for k, p in prompts.items()]
        for f in concurrent.futures.as_completed(futures):
            key, result = f.result()
            results[key] = result

    return results


def parse_json(text: str):
    """Parse JSON from LLM response, stripping markdown fences if present.

    Also unwraps single-key objects that wrap an array, since OpenAI's
    json_object mode forces {} output even when prompts ask for [].
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty response from LLM — no JSON to parse")
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    result = json.loads(text)
    # Unwrap {"key": [...]} → [...] when the prompt expected an array
    if isinstance(result, dict) and len(result) == 1:
        val = next(iter(result.values()))
        if isinstance(val, list):
            return val
    return result
