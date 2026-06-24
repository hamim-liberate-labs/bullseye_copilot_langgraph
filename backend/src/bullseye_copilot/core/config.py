"""
Central configuration. Everything env-derived lives here so the rest of the app
imports settled values rather than re-reading os.getenv all over.

Paths default to this repo's own bundled copies of the prompt, the help-center
snapshot, and the Bullseye MCP server — the repo is self-contained. Override any
of them via env vars if you keep those assets elsewhere.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ── Paths ────────────────────────────────────────────────────────────────────
# this file: <repo>/backend/src/bullseye_copilot/core/config.py
_P = Path(__file__).resolve().parents
PACKAGE_DIR = _P[1]        # src/bullseye_copilot
SRC_DIR = _P[2]            # src
BACKEND_DIR = _P[3]        # backend
REPO_ROOT = _P[4]          # repo root (langgraph-copilot)

# Load the backend's own .env first, then fall back to the repo-root .env for
# shared secrets (ANTHROPIC_API_KEY, BULLSEYE_BASE_URL, …).
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(REPO_ROOT / ".env")

BULLSEYE_BASE_URL = os.getenv("BULLSEYE_BASE_URL")

# The Bullseye MCP server is bundled at the repo root with its own venv. We spawn
# it over stdio and adapt its tools into LangChain (llm/.../tools/bullseye_mcp.py).
MCP_DIR = Path(os.getenv("BULLSEYE_MCP_DIR", str(REPO_ROOT / "bullseye-mcp")))
MCP_PYTHON = (
    MCP_DIR / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
)
MCP_SERVER = MCP_DIR / "server.py"

# The system prompt and help-center snapshot are bundled at the repo root.
PROMPT_PATH = Path(
    os.getenv(
        "BULLSEYE_PROMPT_PATH",
        str(REPO_ROOT / "prompts" / "bullseye_copilot_system_prompt.md"),
    )
)
KNOWLEDGE_DIR = Path(
    os.getenv("BULLSEYE_KNOWLEDGE_DIR", str(REPO_ROOT / "knowledge" / "help"))
)

# Per-chat artifact workspaces: <ARTIFACTS_ROOT>/<chat_id>/<thread-slug>/artifact.html
ARTIFACTS_ROOT = Path(os.getenv("ARTIFACTS_ROOT", str(REPO_ROOT / "artifacts")))

# Built frontend (optional): served by FastAPI in production.
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

# ── Server ───────────────────────────────────────────────────────────────────
# Port 8000 matches the frontend's Vite dev proxy (frontend/vite.config.ts).
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

# ── Agent ────────────────────────────────────────────────────────────────────
# Model aliases the UI may select (mapped to provider + concrete id in
# llm/models.py MODEL_REGISTRY). Anything else falls back to the default so a
# spoofed value can't push an arbitrary model string into the agent.
ALLOWED_MODELS = {"gpt", "sonnet", "opus", "haiku"}
DEFAULT_MODEL = os.getenv("BULLSEYE_MODEL", "gpt")

# Reasoning effort the UI may select. Mapped per-provider in llm/models.py:
# OpenAI -> reasoning_effort, Anthropic -> thinking budget. "minimal" is a real
# GPT level; for Claude (no minimal tier) it degrades to no extended thinking.
ALLOWED_EFFORTS = {"minimal", "low", "medium", "high", "xhigh", "max"}
DEFAULT_EFFORT = os.getenv("BULLSEYE_EFFORT", "low")

# Caps the agent's tool/think loop. One LangGraph "turn" is ~2 graph super-steps
# (model -> tools), so the recursion limit ≈ 2× the number of tool rounds a turn
# may take. Rich artifact turns (fetch several records, run many aggregations,
# build + verify an artifact) legitimately need a few dozen rounds — but hitting
# the limit is handled gracefully (the turn returns its partial work), so this is
# a safety cap, not a hard wall.
MAX_TURNS = int(os.getenv("BULLSEYE_MAX_TURNS", "40"))
RECURSION_LIMIT = MAX_TURNS * 2 + 1

# Confirm-before-write is enforced in the system prompt (prose confirmation).
# Set to "1" to additionally enable the enforced HumanInTheLoopMiddleware
# interrupt — but that requires the frontend to support resume
# (Command(resume=…)). Off by default.
ENABLE_HITL = os.getenv("BULLSEYE_ENABLE_HITL", "0") == "1"

# ── Cost controls ─────────────────────────────────────────────────────────────
# Bound conversation-history growth: once the running message history crosses
# SUMMARY_TRIGGER_TOKENS, older messages are condensed into a summary while the
# most recent SUMMARY_KEEP_MESSAGES are kept verbatim. Short conversations never
# pay the summarization overhead; long ones stop growing linearly. Summaries use
# a cheap model (SUMMARY_MODEL) to keep the overhead small.
ENABLE_SUMMARIZATION = os.getenv("BULLSEYE_ENABLE_SUMMARIZATION", "1") == "1"
SUMMARY_TRIGGER_TOKENS = int(os.getenv("BULLSEYE_SUMMARY_TRIGGER_TOKENS", "20000"))
SUMMARY_KEEP_MESSAGES = int(os.getenv("BULLSEYE_SUMMARY_KEEP_MESSAGES", "20"))
SUMMARY_MODEL = os.getenv("BULLSEYE_SUMMARY_MODEL", "haiku")

# Context editing: the heaviest input is tool-result data accumulating across the
# agent loop. Once the running token count crosses CONTEXT_EDIT_TRIGGER_TOKENS,
# older tool outputs are replaced with a "[cleared]" placeholder (the most recent
# CONTEXT_EDIT_KEEP results stay intact). Safe here because our tool outputs are
# compact summaries pointing at ./data/*.json on disk — the agent can re-read a
# file with bash if it ever needs cleared detail again. Runs before (and cheaper
# than) summarization, so it usually keeps a turn small enough that the heavier
# summarization step never fires.
ENABLE_CONTEXT_EDITING = os.getenv("BULLSEYE_ENABLE_CONTEXT_EDITING", "1") == "1"
# Kept below SUMMARY_TRIGGER_TOKENS so the cheap tool-output clear runs before the
# heavier (LLM-backed) summarization.
CONTEXT_EDIT_TRIGGER_TOKENS = int(os.getenv("BULLSEYE_CONTEXT_EDIT_TRIGGER_TOKENS", "15000"))
CONTEXT_EDIT_KEEP = int(os.getenv("BULLSEYE_CONTEXT_EDIT_KEEP", "3"))

# Cap full artifact rewrites per turn. Each write_file's HTML is a large tool-call
# argument that both costs output tokens and lingers in context (inflating cache
# cost), and models tend to re-write the whole document instead of editing it.
# Past this many write_file calls in a turn, further ones are blocked with a
# message telling the model to use the Edit tool instead. 0 disables the cap.
WRITE_FILE_RUN_LIMIT = int(os.getenv("BULLSEYE_WRITE_FILE_LIMIT", "2"))

# Bash-spiral backstop. A long run of consecutive bash-only steps is almost always
# a debugging spiral (re-running a failing script, probing data field-by-field) —
# the most common way a turn exhausts its step budget and returns partial work. We
# don't hard-cap bash (heavy turns legitimately need several calls); instead, once
# this many consecutive bash-only model steps occur, we inject a one-shot reminder
# telling the model to stop and consolidate into a single script. Re-fires every
# BASH_SPIRAL_REPEAT steps if it keeps going. 0 disables the nudge.
BASH_SPIRAL_THRESHOLD = int(os.getenv("BULLSEYE_BASH_SPIRAL_THRESHOLD", "4"))
BASH_SPIRAL_REPEAT = int(os.getenv("BULLSEYE_BASH_SPIRAL_REPEAT", "3"))


def resolve_model(requested: str | None) -> str:
    return requested if requested in ALLOWED_MODELS else DEFAULT_MODEL


def resolve_effort(requested: str | None) -> str:
    return requested if requested in ALLOWED_EFFORTS else DEFAULT_EFFORT
