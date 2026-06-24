"""
Per-turn token + cost accounting.

Accumulates `usage_metadata` from every model call in a turn (the main agent
model *and* the summarizer), broken down into uncached / cache-read / cache-write
input and output, and estimates USD cost so it lands in the server logs and the
API response. This is how we actually *see* the caching pay off (cache-read
share) and where the tokens go — no LangSmith round-trip needed.

Pricing is approximate Anthropic list pricing (USD per million tokens) and is a
best-effort *estimate* — update PRICES if Anthropic changes rates. cache_write
uses the 5-minute (1.25×) rate, matching our caching middleware's ttl.
"""

# USD per million tokens: (uncached input, output, cache write, cache read).
# "gpt" = gpt-5.4-2026-03-05, OpenAI list pricing (input $2.50, cached input
# $0.25, output $15.00). OpenAI auto-caches (no explicit cache writes), so
# cache_write is set equal to input (it won't be charged separately) and
# cache_read is the discounted cached-input rate.
PRICES = {
    "gpt":    {"input": 2.50, "output": 15.0, "cache_write": 2.50,  "cache_read": 0.25},
    "opus":   {"input": 15.0, "output": 75.0, "cache_write": 18.75, "cache_read": 1.50},
    "sonnet": {"input": 3.0,  "output": 15.0, "cache_write": 3.75,  "cache_read": 0.30},
    "haiku":  {"input": 1.0,  "output": 5.0,  "cache_write": 1.25,  "cache_read": 0.10},
}

# Long-context tier: a single request whose input exceeds this many tokens is
# billed at a multiplied rate for that *whole* request. gpt-5.4 (1.05M context)
# charges 2x input / 1.5x output above 272K input tokens; Claude models have no
# such tier, so the multipliers default to 1x. Keyed by price family.
TIER = {
    "gpt": {"threshold": 272_000, "input_mult": 2.0, "output_mult": 1.5},
}


def _family(model_id: str | None) -> str:
    mid = model_id or ""
    if "gpt" in mid:
        return "gpt"
    for fam in ("opus", "sonnet", "haiku"):
        if fam in mid:
            return fam
    return "sonnet"  # sensible default for cost estimation


class TurnUsage:
    """Running token/cost totals for one chat turn."""

    def __init__(self) -> None:
        self.calls = 0
        self.input = 0
        self.output = 0
        self.cache_read = 0
        self.cache_write = 0
        self.reasoning = 0  # subset of output (OpenAI reasoning models); 0 for Claude
        self.cost = 0.0

    def add(self, message) -> None:
        """Fold one model message's usage_metadata into the totals."""
        um = getattr(message, "usage_metadata", None)
        if not um:
            return
        self.calls += 1
        inp = um.get("input_tokens", 0) or 0
        out = um.get("output_tokens", 0) or 0
        details = um.get("input_token_details") or {}
        cr = details.get("cache_read", 0) or 0
        cw = details.get("cache_creation", 0) or 0
        uncached = max(inp - cr - cw, 0)
        out_details = um.get("output_token_details") or {}
        reasoning = out_details.get("reasoning", 0) or 0

        self.input += inp
        self.output += out
        self.cache_read += cr
        self.cache_write += cw
        self.reasoning += reasoning

        # Providers differ on the key: Anthropic uses "model", OpenAI "model_name".
        meta = getattr(message, "response_metadata", {}) or {}
        model_id = meta.get("model") or meta.get("model_name")
        fam = _family(model_id)
        p = PRICES[fam]

        # Long-context tier is decided per request, on that request's total input
        # tokens (cached + uncached), and multiplies the rate for the whole call.
        in_mult = out_mult = 1.0
        tier = TIER.get(fam)
        if tier and inp > tier["threshold"]:
            in_mult = tier["input_mult"]
            out_mult = tier["output_mult"]

        self.cost += (
            uncached * p["input"] * in_mult
            + cr * p["cache_read"] * in_mult
            + cw * p["cache_write"] * in_mult
            + out * p["output"] * out_mult
        ) / 1_000_000

    @property
    def cache_hit_pct(self) -> float:
        return (self.cache_read / self.input * 100) if self.input else 0.0

    def summary(self) -> str:
        # `reasoning` is a subset of output tokens — shown only when present
        # (OpenAI reasoning models), omitted for Claude which doesn't report it.
        out = f"out={self.output}"
        if self.reasoning:
            out += f" (reasoning={self.reasoning})"
        return (
            f"in={self.input} {out} "
            f"cache_read={self.cache_read} cache_write={self.cache_write} "
            f"({self.cache_hit_pct:.0f}% of input cached) "
            f"~${self.cost:.4f} est over {self.calls} model calls"
        )
