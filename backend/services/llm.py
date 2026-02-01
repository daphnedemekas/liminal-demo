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
from typing import Optional

logger = logging.getLogger(__name__)

_client = None
PROVIDER = os.environ.get("LLM_PROVIDER", "openai")
MODEL = os.environ.get("LLM_MODEL", "gpt-4o")


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
    """Single-turn LLM call. Returns the text response. Raises on failure."""
    client = _get_client()
    m = model or MODEL

    if PROVIDER == "anthropic":
        response = client.messages.create(
            model=m,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    else:
        response = client.chat.completions.create(
            model=m,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
        )
        return response.choices[0].message.content or ""


def chat_messages(system_prompt: str, messages: list[dict], model: Optional[str] = None, json_mode: bool = False) -> str:
    """Multi-turn LLM call. messages is a list of {role, content} dicts."""
    client = _get_client()
    m = model or MODEL

    if PROVIDER == "anthropic":
        response = client.messages.create(
            model=m,
            max_tokens=2048,
            system=system_prompt,
            messages=messages,
        )
        return response.content[0].text
    else:
        all_messages = [{"role": "system", "content": system_prompt}] + messages
        kwargs = dict(model=m, messages=all_messages, max_tokens=2048)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""


def chat_json(prompt: str, model: Optional[str] = None):
    """Single-turn LLM call that parses the response as JSON. Raises on failure."""
    text = chat(prompt, model=model)
    return parse_json(text)


def parse_json(text: str):
    """Parse JSON from LLM response, stripping markdown fences if present."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)
