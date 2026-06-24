"""Model factory: resolve the UI's model alias + effort level to a configured
chat model, across providers (Anthropic Claude and OpenAI GPT).

Each alias maps to (provider, model_id). The `effort` knob is translated to the
provider's own reasoning control:
  - Anthropic: extended thinking with a token budget (0 = off).
  - OpenAI: the `reasoning_effort` parameter (minimal/low/medium/high).
"""

from langchain_anthropic import ChatAnthropic

from bullseye_copilot.core.config import resolve_effort, resolve_model

# UI alias -> (provider, concrete model id).
MODEL_REGISTRY: dict[str, tuple[str, str]] = {
    "gpt": ("openai", "gpt-5.4-2026-03-05"),
    "opus": ("anthropic", "claude-opus-4-8"),
    "sonnet": ("anthropic", "claude-sonnet-4-6"),
    "haiku": ("anthropic", "claude-haiku-4-5"),
}

# Anthropic effort -> extended-thinking budget in tokens (0 disables thinking).
# Claude has no "minimal" tier, so it maps to no extended thinking (like "low").
THINKING_BUDGET = {
    "minimal": 0,
    "low": 0,
    "medium": 4_000,
    "high": 8_000,
    "xhigh": 16_000,
    "max": 32_000,
}

# OpenAI effort -> reasoning_effort level. Verified by a live API call against
# gpt-5.4-2026-03-05, which accepts: none, low, medium, high, xhigh (NOTE: it
# rejects "minimal" even though the SDK's generic literal lists it). So our UI
# "Minimal" maps to the model's true floor "none" (no reasoning), and "max" maps
# to the top level "xhigh".
OPENAI_REASONING_EFFORT = {
    "minimal": "none",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "xhigh",
    "max": "xhigh",
}

# Output cap when thinking is off; with thinking on we use budget + this headroom.
BASE_MAX_TOKENS = 16_000


def provider_of(model_alias: str | None) -> str:
    """Provider ('anthropic' | 'openai') for a (possibly None) alias."""
    return MODEL_REGISTRY[resolve_model(model_alias)][0]


def build_model(model_alias: str | None, effort: str | None):
    alias = resolve_model(model_alias)
    eff = resolve_effort(effort)
    provider, model_id = MODEL_REGISTRY[alias]

    if provider == "openai":
        # Lazy import so the OpenAI dependency is only required when GPT is used.
        from langchain_openai import ChatOpenAI

        # Reasoning models reject a custom temperature, so we don't set one.
        # use_responses_api=True: gpt-5.4 rejects function tools + reasoning_effort
        # on /v1/chat/completions and requires the Responses API (/v1/responses);
        # our agent always binds tools, so we route GPT through it.
        # stream_usage=True so token usage is reported during streaming (OpenAI
        # omits it otherwise) — our per-turn cost logging depends on it.
        return ChatOpenAI(
            model=model_id,
            reasoning_effort=OPENAI_REASONING_EFFORT[eff],
            use_responses_api=True,
            stream_usage=True,
        )

    budget = THINKING_BUDGET[eff]
    if budget > 0:
        # Extended thinking requires temperature unset (defaults to 1).
        return ChatAnthropic(
            model=model_id,
            max_tokens=budget + BASE_MAX_TOKENS,
            thinking={"type": "enabled", "budget_tokens": budget},
        )
    return ChatAnthropic(model=model_id, max_tokens=BASE_MAX_TOKENS, temperature=0)
