"""
App + config: the single FastMCP instance, env-derived settings, and the logger.
Kept free of other `core` imports so `helpers`/`session` can import it without a cycle.
"""

import os
import logging
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP
from dotenv import load_dotenv

# Load .env from the package root (this file is in bullseye-mcp/core/), not the
# launcher's cwd — Claude Code spawns the server from the project root.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE = os.getenv("BULLSEYE_BASE_URL")
TIMEOUT = float(os.getenv("BULLSEYE_TIMEOUT", "30"))

# Gateway mode (set): bulk tool results offload to <workdir>/data/*.json.
# Unset (interactive use): tools return full payloads inline. See helpers.offload.
WORKDIR: Optional[str] = os.getenv("BULLSEYE_WORKDIR") or None

# In gateway mode, payloads smaller than this (serialized bytes) are returned
# inline anyway — not worth a file the model has to read back.
OFFLOAD_MIN_BYTES = int(os.getenv("BULLSEYE_OFFLOAD_MIN_BYTES", "4096"))

logging.basicConfig(
    level=os.getenv("BULLSEYE_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [bullseye-mcp] %(message)s",
)
log = logging.getLogger("bullseye-mcp")

mcp = FastMCP("Bullseye Copilot")
