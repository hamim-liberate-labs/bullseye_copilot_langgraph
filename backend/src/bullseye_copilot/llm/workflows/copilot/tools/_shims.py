"""
Windows command shims for the bash tool.

The system prompt (written for a unix-like environment) tells the agent to use
`python3` and `grep`. On Windows neither exists on the default `cmd.exe` PATH
(`python` exists, `python3`/`grep` do not). Rather than fork the prompt, we
materialise a tiny shim directory and prepend it to the subprocess PATH so those
exact commands resolve:

  • python3 → the current backend interpreter (sys.executable)
  • grep    → a minimal Python implementation covering `-r`, `-i`, `-n`

On non-Windows hosts both already exist, so this is a no-op.
"""

import os
import sys
import tempfile
from pathlib import Path

_GREP_PY = r'''
import os, re, sys

args = sys.argv[1:]
flags, pattern, paths = set(), None, []
for a in args:
    if a.startswith("-") and len(a) > 1 and not a[1:].isdigit():
        flags.update(a[1:])
    elif pattern is None:
        pattern = a
    else:
        paths.append(a)

if pattern is None:
    sys.exit(2)
if not paths:
    paths = ["."]

ignore_case = "i" in flags
show_line = "n" in flags
recursive = "r" in flags or "R" in flags
try:
    rx = re.compile(pattern, re.I if ignore_case else 0)
except re.error:
    rx = re.compile(re.escape(pattern), re.I if ignore_case else 0)


def iter_files(p):
    if os.path.isdir(p):
        if recursive:
            for root, _, files in os.walk(p):
                for f in files:
                    yield os.path.join(root, f)
    else:
        yield p


found = False
for p in paths:
    for fp in iter_files(p):
        try:
            with open(fp, encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh, 1):
                    if rx.search(line):
                        found = True
                        loc = f"{fp}:{i}:" if show_line else f"{fp}:"
                        sys.stdout.write(loc + line.rstrip("\n") + "\n")
        except (OSError, UnicodeError):
            continue

sys.exit(0 if found else 1)
'''


def ensure_shims() -> str | None:
    """Create the shim dir (idempotently) and return its path, or None when no
    shims are needed (non-Windows)."""
    if os.name != "nt":
        return None

    shim_dir = Path(tempfile.gettempdir()) / "bullseye_copilot_shims"
    shim_dir.mkdir(parents=True, exist_ok=True)
    py = sys.executable

    grep_py = shim_dir / "grep.py"
    grep_py.write_text(_GREP_PY, encoding="utf-8")

    # `.cmd` shims so the bare names resolve under cmd.exe. %* forwards args.
    (shim_dir / "python3.cmd").write_text(f'@echo off\r\n"{py}" %*\r\n', encoding="utf-8")
    (shim_dir / "grep.cmd").write_text(
        f'@echo off\r\n"{py}" "{grep_py}" %*\r\n', encoding="utf-8"
    )
    return str(shim_dir)


def shimmed_env() -> dict:
    """A copy of os.environ with the shim dir prepended to PATH (Windows only)."""
    env = dict(os.environ)
    shim_dir = ensure_shims()
    if shim_dir:
        env["PATH"] = shim_dir + os.pathsep + env.get("PATH", "")
    return env
