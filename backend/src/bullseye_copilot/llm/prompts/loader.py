"""System-prompt loading + fill.

Uses the bundled prompt file (prompts/bullseye_copilot_system_prompt.md) and
fills its `{{...}}` placeholders (user, school, current date, base URL) per turn.
"""

from datetime import date

from bullseye_copilot.core.config import BULLSEYE_BASE_URL, PROMPT_PATH

PROMPT_TEMPLATE = PROMPT_PATH.read_text(encoding="utf-8")

# Backend-only addendum (kept out of the shared prompt file). Artifact HTML is
# generated as tool-call output, which is the single biggest output-token cost
# and latency driver — so steer the model to generate it once and to iterate with
# small edits rather than full rewrites.
_ARTIFACT_EFFICIENCY_ADDENDUM = """

## Artifact efficiency (important)

Writing an artifact's HTML is by far your most expensive and slowest action — the
whole document is generated token by token. Follow this order strictly:

1. **Finish ALL data work first.** Make every Bullseye call and run every
   python/bash aggregation you need *before* you write any artifact HTML. Do not
   write the artifact until every number, label, and series it will display has
   already been computed and is sitting in your tool results.
2. **Then write the artifact exactly once** — one complete `Write` of
   `./<thread-slug>/artifact.html`. Writing that file more than once in a turn is
   wasteful and should not happen; if you catch yourself about to re-Write it,
   stop and aggregate what's missing first, then do the single write.
3. **After that one write, change it only with the Edit tool** — small, targeted
   diffs (resize a chart, add a panel, fix a label). Never re-Write the whole
   document for a change. If a Write is ever refused because you've already
   written the artifact, that's expected — switch to the Edit tool and continue.

Keep artifacts as compact as the content honestly allows — richness comes from
the data, not from verbose or decorative markup.

## Work in as few steps as possible

Every tool round-trip costs real money and time, so minimize them:

- **Do all your number-crunching in ONE script.** Once the data files exist, write
  a single `./scripts/*.py` that computes *every* figure, trend, and series the
  answer needs and prints them together — then run it once. Do not run a long
  series of small `python3 -c` or bash commands.
- **Request independent reads together, in parallel.** When you need several
  things that don't depend on each other (multiple session pages, several people),
  call those tools in the same step, not one at a time.
- Plan the whole answer up front, gather and compute in as few rounds as you can,
  then write the single artifact. Fewer, larger steps beat many small ones.

### Do not loop on `bash`

A long run of `bash` calls is almost always a debugging spiral, and it is the
single most common way to exhaust the step budget and return unfinished work.
Each call is a full, slow round-trip — treat them as scarce:

- **Inspect the data shape ONCE.** In one command, print the keys and a sample row
  of a single `./data/*.json`. Understand the structure from that, then write the
  real script. Never probe field-by-field across many commands.
- **Write the aggregation script once and run it once.** Re-running it with small
  tweaks *is* the spiral.
- **When a script fails, read the WHOLE error, fix the script, and rerun at most
  once or twice.** If it still fails after two reruns, stop patching one error at a
  time — re-read the data shape and rewrite the script properly in a single pass.
- **Never use `bash` to "verify", "preview", or re-render the finished artifact.**
  Writing the file is enough; opening or re-running it just burns steps.

## Design guidance

There is no separate "frontend-design skill" to invoke in this environment.
Ignore any instruction above to call it. Your design guidance is the **Bullseye
artifact design system** described earlier in this prompt (brand palette, fonts,
Chart.js rules, responsive layout) — apply it directly when building or restyling
an artifact.
"""


def build_system_prompt(user: dict | None) -> str:
    user = user or {}
    schools = user.get("schools") or []
    # Prefer the active school Bullseye returned at sign-in; fall back to the
    # first listed school only if it's missing. Schools use `display_name`.
    school = user.get("current_school") or (schools[0] if schools else {})
    persona_role = "admin" if user.get("admin") else "observer"

    replacements = {
        "{{user_name}}": user.get("full_name") or "Unknown user",
        "{{user_id}}": str(user.get("id") or ""),
        "{{persona_role}}": persona_role,
        "{{school_name}}": school.get("display_name") or school.get("name") or "",
        "{{school_id}}": str(school.get("id") or ""),
        "{{current_date}}": date.today().isoformat(),
        "{{base_url}}": BULLSEYE_BASE_URL or "",
    }
    prompt = PROMPT_TEMPLATE
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)
    return prompt + _ARTIFACT_EFFICIENCY_ADDENDUM
