"""Path-confinement tests for the workspace file tools.

These invoke the tools directly (no LLM, no API key needed):
    python -m pytest tests/unit/test_file_scope.py
    python tests/unit/test_file_scope.py
"""

import sys
import tempfile
from pathlib import Path

# Make `bullseye_copilot` importable when run as a plain script (no install).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from bullseye_copilot.llm.workflows.copilot.tools.files import make_file_tools  # noqa: E402


def _tools(workdir: Path, read_root: Path):
    by_name = {t.name: t for t in make_file_tools(workdir, read_roots=[read_root])}
    return by_name["read_file"], by_name["write_file"], by_name["edit_file"]


def test_confinement():
    workdir = Path(tempfile.mkdtemp(prefix="lg_scope_"))
    help_root = Path(tempfile.mkdtemp(prefix="lg_help_"))
    (help_root / "INDEX.md").write_text("help index", encoding="utf-8")
    outside = Path(tempfile.gettempdir()) / "lg_scope_outside.html"
    outside.unlink(missing_ok=True)

    read_file, write_file, edit_file = _tools(workdir, help_root)

    checks = []

    # 1. write inside the workspace — allowed
    write_file.invoke({"path": "./inside/artifact.html", "content": "<h1>ok</h1>"})
    checks.append(("write inside allowed", (workdir / "inside" / "artifact.html").is_file()))

    # 2. write outside (absolute) — denied, no file created
    r = write_file.invoke({"path": str(outside), "content": "<h1>nope</h1>"})
    checks.append(("write outside denied", r.startswith("DENIED") and not outside.exists()))

    # 3. parent-escape write — denied
    r = write_file.invoke({"path": "../escape.txt", "content": "x"})
    checks.append(("parent escape denied", r.startswith("DENIED")))

    # 4. read the help snapshot (read-only root) — allowed
    r = read_file.invoke({"path": str(help_root / "INDEX.md")})
    checks.append(("read help-root allowed", r == "help index"))

    # 5. read outside any root — denied
    r = read_file.invoke({"path": "/etc/hostname"})
    checks.append(("read outside denied", r.startswith(("DENIED", "NOT FOUND"))))

    outside.unlink(missing_ok=True)

    print("--- file-scope checks ---")
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    assert ok, "path confinement FAILED"
    print("\nPATH SCOPING WORKS")


if __name__ == "__main__":
    test_confinement()
