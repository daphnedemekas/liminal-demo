"""Per-domain prompt configurations.

Each domain module exports a DOMAIN_PROMPTS dict with domain-specific
guidance that gets injected into the generic discovery prompts.
"""

from backend.prompts.domains.work import DOMAIN_PROMPTS as WORK_PROMPTS
from backend.prompts.domains.social import DOMAIN_PROMPTS as SOCIAL_PROMPTS
from backend.prompts.domains.studies import DOMAIN_PROMPTS as STUDIES_PROMPTS
from backend.prompts.domains.health import DOMAIN_PROMPTS as HEALTH_PROMPTS
from backend.prompts.domains.hobbies import DOMAIN_PROMPTS as HOBBIES_PROMPTS
from backend.prompts.domains.money import DOMAIN_PROMPTS as MONEY_PROMPTS
from backend.prompts.domains.mental_health import DOMAIN_PROMPTS as MENTAL_HEALTH_PROMPTS

DOMAIN_PROMPT_REGISTRY: dict[str, dict] = {
    "work": WORK_PROMPTS,
    "social": SOCIAL_PROMPTS,
    "studies": STUDIES_PROMPTS,
    "health": HEALTH_PROMPTS,
    "hobbies": HOBBIES_PROMPTS,
    "money": MONEY_PROMPTS,
    "mental_health": MENTAL_HEALTH_PROMPTS,
}


def get_domain_prompts(domain: str) -> dict:
    """Get domain-specific prompts, falling back to empty dict."""
    return DOMAIN_PROMPT_REGISTRY.get(domain, {})
