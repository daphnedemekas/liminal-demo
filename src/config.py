"""
Configuration loader for the curiosity discovery system.
"""
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv


# Load environment variables
load_dotenv()

_APP_CONFIG_CACHE: Optional[Dict[str, Any]] = None


def get_api_key() -> str:
    """Get Anthropic API key from environment."""
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY not found in environment variables. "
            "Please create a .env file with your API key (see .env.example)"
        )
    return api_key


def get_openai_api_key() -> str:
    """Get OpenAI API key from environment."""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY not found in environment variables. "
            "Please create a .env file with your API key (see .env.example)"
        )
    return api_key


def get_cerebras_api_key() -> str:
    """Get Cerebras API key from environment."""
    api_key = os.getenv('CEREBRAS_API_KEY')
    if not api_key:
        raise ValueError(
            "CEREBRAS_API_KEY not found in environment variables. "
            "Please create a .env file with your API key (see .env.example)"
        )
    return api_key


def reset_app_config_cache() -> None:
    """Clear cached config (useful for benchmarks that sweep many configs in one process)."""
    global _APP_CONFIG_CACHE
    _APP_CONFIG_CACHE = None


def load_app_config(config_path: Optional[str] = None, force_reload: bool = False) -> Dict[str, Any]:
    """
    Load `config.yaml` from the project root (cached).

    This is intentionally lightweight and optional: if the file is missing or invalid,
    callers should fall back to sensible defaults.
    """
    global _APP_CONFIG_CACHE
    if _APP_CONFIG_CACHE is not None and not force_reload:
        return _APP_CONFIG_CACHE

    try:
        if config_path is not None:
            path = Path(config_path)
        else:
            # Allow benchmarks to override config path without modifying repo files.
            env_path = os.getenv("LIMINAL_CONFIG_PATH")
            if env_path:
                path = Path(env_path)
            else:
                # src/config.py -> project root is one level up from src/
                path = Path(__file__).resolve().parent.parent / "config.yaml"

        if not path.exists():
            _APP_CONFIG_CACHE = {}
            return _APP_CONFIG_CACHE

        with open(path, "r", encoding="utf-8") as f:
            _APP_CONFIG_CACHE = yaml.safe_load(f) or {}
            return _APP_CONFIG_CACHE
    except Exception:
        _APP_CONFIG_CACHE = {}
        return _APP_CONFIG_CACHE


def get_cfg(*keys: str, default: Any = None) -> Any:
    """
    Safe nested config lookup.

    Example:
        get_cfg("models", "ranker", "controller", "name", default="claude-sonnet-4-20250514")
    """
    cfg: Any = load_app_config()
    for k in keys:
        if not isinstance(cfg, dict) or k not in cfg:
            return default
        cfg = cfg[k]
    return cfg


def get_model_name(role: str, task: Optional[str] = None, default: str = "claude-sonnet-4-20250514") -> str:
    """
    Resolve model name for a given role/task from config.yaml.

    Supported shapes:
      models:
        ranker:
          name: "..."
          controller:
            name: "..."
        interviewer:
          name: "..."
    """
    if task:
        name = get_cfg("models", role, task, "name", default=None)
        if isinstance(name, str) and name.strip():
            return name
    name = get_cfg("models", role, "name", default=None)
    if isinstance(name, str) and name.strip():
        return name
    return default


def get_conversation_max_turns(default: int = 8) -> int:
    val = get_cfg("conversation", "max_turns", default=default)
    try:
        return int(val)
    except Exception:
        return default
