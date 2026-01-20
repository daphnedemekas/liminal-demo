"""
Anthropic/Claude API client wrapper with error handling and retry logic.
"""
import json
import time
from typing import List, Dict, Optional, Tuple, Generator
from anthropic import Anthropic
from openai import OpenAI

from .config import get_api_key, get_openai_api_key, get_cerebras_api_key, get_cfg


class LLMClient:
    """Multi-provider LLM client wrapper with retry logic and error handling."""

    def __init__(self):
        self.anthropic_client = Anthropic(api_key=get_api_key())
        openai_timeout_s = get_cfg("providers", "openai", "timeout_s", default=20)
        cerebras_timeout_s = get_cfg("providers", "cerebras", "timeout_s", default=20)

        # OpenAI-compatible SDK clients. Keep timeouts bounded to avoid 60s+ hangs in interactive loops.
        self.openai_client = OpenAI(api_key=get_openai_api_key(), timeout=openai_timeout_s)

        cerebras_base_url = get_cfg("providers", "cerebras", "base_url", default="https://api.cerebras.ai/v1")
        self.cerebras_client = OpenAI(
            api_key=get_cerebras_api_key(),
            base_url=cerebras_base_url,
            timeout=cerebras_timeout_s,
        )
        self.total_tokens = 0

    def _resolve_provider_and_model(self, model: str) -> Tuple[str, str]:
        """
        Resolve provider from `model`.

        Supported forms:
        - "anthropic:claude-..."
        - "openai:gpt-..."
        - "cerebras:llama-..."
        - If no prefix is provided, infer:
          - "claude-..." => anthropic
          - otherwise => openai (default)
        """
        if ":" in model:
            provider, name = model.split(":", 1)
            return provider.strip().lower(), name.strip()

        m = model.strip().lower()
        if m.startswith("claude"):
            return "anthropic", model
        return "openai", model

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        max_retries: int = 3
    ) -> str:
        """
        Make a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            max_retries: Number of retry attempts on failure

        Returns:
            Response content as string
        """
        for attempt in range(max_retries):
            try:
                provider, model_name = self._resolve_provider_and_model(model)

                if provider == "anthropic":
                    # Extract system message if present (Anthropic uses separate `system`)
                    system_message = None
                    chat_messages = []
                    for msg in messages:
                        if msg["role"] == "system":
                            system_message = msg["content"]
                        else:
                            chat_messages.append({"role": msg["role"], "content": msg["content"]})

                    kwargs = {
                        "model": model_name,
                        "messages": chat_messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    }
                    if system_message:
                        kwargs["system"] = system_message

                    response = self.anthropic_client.messages.create(**kwargs)

                    if hasattr(response, "usage"):
                        self.total_tokens += response.usage.input_tokens + response.usage.output_tokens

                    return response.content[0].text

                # OpenAI-compatible providers (OpenAI + Cerebras)
                client = self.cerebras_client if provider == "cerebras" else self.openai_client

                # GPT-5 and o-series models have special requirements:
                # - use max_completion_tokens instead of max_tokens
                # - only support temperature=1 (don't pass custom temperature)
                is_restricted_model = model_name.startswith("gpt-5") or model_name.startswith("o1") or model_name.startswith("o3")
                
                kwargs = {
                    "model": model_name,
                    "messages": messages,
                }
                
                # Only pass temperature for models that support it
                if not is_restricted_model:
                    kwargs["temperature"] = temperature
                
                if is_restricted_model:
                    kwargs["max_completion_tokens"] = max_tokens
                else:
                    kwargs["max_tokens"] = max_tokens

                resp = client.chat.completions.create(**kwargs)

                usage = getattr(resp, "usage", None)
                if usage is not None:
                    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                    self.total_tokens += prompt_tokens + completion_tokens

                return resp.choices[0].message.content or ""

            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                # Check for rate limit errors (429) and use longer backoff
                error_str = str(e).lower()
                is_rate_limit = '429' in error_str or 'rate' in error_str or 'too many' in error_str
                if is_rate_limit:
                    # Longer backoff for rate limits: 5s, 15s, 45s
                    delay = 5 * (3 ** attempt)
                    print(f"[LLM] Rate limit hit, waiting {delay}s before retry {attempt + 1}/{max_retries}")
                else:
                    # Standard exponential backoff: 1s, 2s, 4s
                    delay = 2 ** attempt
                time.sleep(delay)

        raise RuntimeError("Failed to get response after retries")

    def chat_with_json(
        self,
        messages: List[Dict[str, str]],
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.3,
        max_tokens: int = 2000,
        max_retries: int = 3,
        json_top_level: str = "any",  # "object" | "array" | "any"
    ) -> dict:
        """
        Make a chat completion request expecting JSON response.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name to use
            temperature: Sampling temperature (lower for JSON)
            max_tokens: Maximum tokens in response
            max_retries: Number of retry attempts on failure

        Returns:
            Parsed JSON response as dictionary
        """
        # Add JSON instruction to the last message (prompt-based fallback).
        if messages:
            last_msg = messages[-1]["content"]
            messages[-1]["content"] = (
                last_msg
                + "\n\nRespond with valid JSON only. Do not include any text outside the JSON structure."
            )

        llm_start = time.time()  # Track total time across retries
        provider, model_name = self._resolve_provider_and_model(model)  # Resolve once outside loop
        for attempt in range(max_retries):
            try:
                if attempt == 0:
                    print(f"[LLM] Starting {provider}:{model_name} call...")
                else:
                    print(f"[LLM] Retrying {provider}:{model_name} call (attempt {attempt + 1}/{max_retries})...")
                attempt_start = time.time()

                # For OpenAI-compatible providers, try structured JSON mode when supported.
                if provider in ("openai", "cerebras"):
                    client = self.cerebras_client if provider == "cerebras" else self.openai_client
                    try:
                        # NOTE: response_format currently only supports forcing a JSON *object*.
                        # Many of our ranker tasks return a top-level JSON array. For those, do not
                        # force response_format; rely on prompt-only parsing.
                        
                        # GPT-5 and o-series models have special requirements
                        is_restricted_model = model_name.startswith("gpt-5") or model_name.startswith("o1") or model_name.startswith("o3")
                        
                        kwargs = dict(
                            model=model_name,
                            messages=messages,
                        )
                        
                        # Only pass temperature for models that support it
                        if not is_restricted_model:
                            kwargs["temperature"] = temperature
                        
                        if is_restricted_model:
                            kwargs["max_completion_tokens"] = max_tokens
                        else:
                            kwargs["max_tokens"] = max_tokens
                            
                        if json_top_level == "object":
                            kwargs["response_format"] = {"type": "json_object"}

                        resp = client.chat.completions.create(**kwargs)
                        response_text = resp.choices[0].message.content or ""

                        usage = getattr(resp, "usage", None)
                        if usage is not None:
                            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                            completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                            self.total_tokens += prompt_tokens + completion_tokens
                    except TypeError:
                        # Some providers/models may not support response_format; fall back to prompt-only.
                        response_text = self.chat(
                            messages=messages,
                            model=model,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            max_retries=1
                        )
                else:
                    response_text = self.chat(
                        messages=messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        max_retries=1
                    )

                # Try to extract JSON from response
                # Sometimes Claude wraps JSON in markdown code blocks or adds text
                json_str = response_text.strip()

                # Fast-path: if the model actually followed instructions, this just works.
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass

                if '```json' in json_str:
                    # Extract JSON from code block
                    start = json_str.find('```json') + 7
                    end = json_str.find('```', start)
                    json_str = json_str[start:end].strip()
                elif '```' in json_str:
                    # Extract from generic code block
                    start = json_str.find('```') + 3
                    end = json_str.find('```', start)
                    json_str = json_str[start:end].strip()
                else:
                    # Fallback boundary extraction.
                    # IMPORTANT: avoid bracket/brace *depth counting* because it breaks on brackets inside strings.
                    first_brace = json_str.find("{")
                    last_brace = json_str.rfind("}")
                    first_bracket = json_str.find("[")
                    last_bracket = json_str.rfind("]")

                    if json_top_level == "array":
                        if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
                            json_str = json_str[first_bracket:last_bracket + 1]
                    elif json_top_level == "object":
                        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                            json_str = json_str[first_brace:last_brace + 1]
                    else:
                        # any: prefer whichever starts first
                        if first_bracket != -1 and (first_brace == -1 or first_bracket < first_brace):
                            if last_bracket != -1 and last_bracket > first_bracket:
                                json_str = json_str[first_bracket:last_bracket + 1]
                        elif first_brace != -1:
                            if last_brace != -1 and last_brace > first_brace:
                                json_str = json_str[first_brace:last_brace + 1]

                elapsed = time.time() - attempt_start
                total_elapsed = time.time() - llm_start
                print(f"[LLM] {provider}:{model_name} completed in {elapsed:.2f}s (total: {total_elapsed:.2f}s)")
                return json.loads(json_str)

            except json.JSONDecodeError as e:
                elapsed = time.time() - attempt_start
                total_elapsed = time.time() - llm_start
                print(f"[LLM] {provider}:{model_name} JSON decode error after {elapsed:.2f}s (total: {total_elapsed:.2f}s): {e}")
                # If JSON parsing fails, retry
                if attempt == max_retries - 1:
                    raise ValueError(f"Failed to parse JSON response: {e}\n\nResponse was:\n{response_text}")
                time.sleep(2 ** attempt)

            except Exception as e:
                elapsed = time.time() - attempt_start
                total_elapsed = time.time() - llm_start
                if attempt == max_retries - 1:
                    print(f"[LLM] {provider}:{model_name} failed after {elapsed:.2f}s (total: {total_elapsed:.2f}s): {e}")
                    raise
                # Check for rate limit errors (429) and use longer backoff
                error_str = str(e).lower()
                is_rate_limit = '429' in error_str or 'rate' in error_str or 'too many' in error_str
                if is_rate_limit:
                    delay = 5 * (3 ** attempt)  # 5s, 15s, 45s
                    print(f"[LLM] Rate limit hit after {elapsed:.2f}s (total: {total_elapsed:.2f}s), waiting {delay}s before retry {attempt + 1}/{max_retries}")
                else:
                    delay = 2 ** attempt
                    print(f"[LLM] Error after {elapsed:.2f}s (total: {total_elapsed:.2f}s), retrying in {delay}s...")
                time.sleep(delay)

        raise RuntimeError("Failed to get JSON response after retries")

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> Generator[str, None, None]:
        """
        Stream a chat completion response, yielding chunks as they arrive.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Yields:
            Text chunks as they stream in
        """
        provider, model_name = self._resolve_provider_and_model(model)

        if provider == "anthropic":
            # Extract system message if present
            system_message = None
            chat_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    system_message = msg["content"]
                else:
                    chat_messages.append({"role": msg["role"], "content": msg["content"]})

            kwargs = {
                "model": model_name,
                "messages": chat_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if system_message:
                kwargs["system"] = system_message

            with self.anthropic_client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    yield text

        else:
            # OpenAI-compatible providers (OpenAI + Cerebras)
            client = self.cerebras_client if provider == "cerebras" else self.openai_client

            # GPT-5 and o-series models have special requirements
            is_restricted_model = model_name.startswith("gpt-5") or model_name.startswith("o1") or model_name.startswith("o3")
            
            kwargs = {
                "model": model_name,
                "messages": messages,
                "stream": True,
            }
            
            # Only pass temperature for models that support it
            if not is_restricted_model:
                kwargs["temperature"] = temperature
            
            if is_restricted_model:
                kwargs["max_completion_tokens"] = max_tokens
            else:
                kwargs["max_tokens"] = max_tokens

            stream = client.chat.completions.create(**kwargs)

            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

    def get_total_tokens(self) -> int:
        """Get total tokens used across all requests."""
        return self.total_tokens

    def reset_token_count(self):
        """Reset token counter."""
        self.total_tokens = 0
