"""Per-domain prompt configurations.

Each domain module exports a DOMAIN_PROMPTS dict with domain-specific
guidance that gets injected into the generic discovery prompts.
"""

from backend.prompts.domains.work import DOMAIN_PROMPTS as WORK_PROMPTS
from backend.prompts.domains.studies import DOMAIN_PROMPTS as LEARNING_PROMPTS
from backend.prompts.domains.health import DOMAIN_PROMPTS as HEALTH_PROMPTS
from backend.prompts.domains.hobbies import DOMAIN_PROMPTS as CREATIVE_PROMPTS
from backend.prompts.domains.money import DOMAIN_PROMPTS as MONEY_PROMPTS
from backend.prompts.domains.mental_health import DOMAIN_PROMPTS as MIND_PROMPTS

DOMAIN_PROMPT_REGISTRY: dict[str, dict] = {
    "work": WORK_PROMPTS,
    "learning": LEARNING_PROMPTS,
    "health": HEALTH_PROMPTS,
    "creative": CREATIVE_PROMPTS,
    "money": MONEY_PROMPTS,
    "mind": MIND_PROMPTS,
}


def get_domain_prompts(domain: str) -> dict:
    """Get domain-specific prompts, falling back to empty dict."""
    return DOMAIN_PROMPT_REGISTRY.get(domain, {})
