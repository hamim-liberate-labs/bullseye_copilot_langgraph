"""
Bash / Python execution tool, confined to the conversation workspace.

The agent uses this to aggregate `./data/*.json` with `python3` and to `grep`
the `./help` snapshot.

⚠️  SECURITY STATUS — read this. This tool runs commands with `cwd` set to the
workspace but does **NOT** provide an OS-level sandbox: a determined command
could read outside the workspace or reach the network. This secure sandbox is
**the single hardest part of the project** and must be hardened before any real
deployment. Recommended hardening (Linux): run each command inside `bubblewrap`
or `nsjail` with no network namespace and a read-only bind of only the workspace
(and ./help), or run the whole backend in a locked-down container.
"""

import asyncio
import logging
import subprocess
from pathlib import Path

from langchain_core.tools import StructuredTool

from ._shims import shimmed_env

log = logging.getLogger("copilot.bash")

_TIMEOUT_SECONDS = 60
_MAX_OUTPUT_BYTES = 60_000


def make_bash_tool(workdir: Path) -> StructuredTool:
    def _run_blocking(command: str) -> tuple[int, str]:
        """Run the command synchronously and return (returncode, merged output).

        Deliberately uses the blocking `subprocess` API rather than
        `asyncio.create_subprocess_shell`: under uvicorn on Windows the running
        event loop is a SelectorEventLoop, whose subprocess transport is not
        implemented (raises NotImplementedError). Running in a worker thread via
        `asyncio.to_thread` (below) sidesteps the loop entirely and is portable
        across platforms.
        """
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(workdir),
                env=shimmed_env(),  # makes `python3`/`grep` resolve on Windows
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return -1, f"ERROR: command timed out after {_TIMEOUT_SECONDS}s"
        except OSError as e:
            return -1, f"ERROR launching command: {e}"
        return proc.returncode, proc.stdout.decode("utf-8", errors="replace")

    async def bash(command: str) -> str:
        """Run a shell command in your private workspace (cwd is your workspace
        root). Use `python3` to aggregate ./data/*.json — for anything beyond a
        one-liner, write the script to ./scripts/<name>.py and run it — and `grep`
        to search ./help. The environment is meant to be offline and confined to
        your workspace; never assume network access.

        Args:
            command: The shell command to execute.
        """
        rc, text = await asyncio.to_thread(_run_blocking, command)
        if len(text) > _MAX_OUTPUT_BYTES:
            text = text[:_MAX_OUTPUT_BYTES] + "\n[output truncated]"
        return text if rc == 0 else f"[exit {rc}]\n{text}"

    return StructuredTool.from_function(coroutine=bash, name="bash")
