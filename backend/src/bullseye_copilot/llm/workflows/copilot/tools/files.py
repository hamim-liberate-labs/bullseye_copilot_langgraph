"""
Workspace-scoped file tools (Read / Write / Edit).

These replace the Agent SDK's built-in file tools and reproduce its isolation
boundary: the agent may only touch paths **inside its per-conversation
workspace** (plus read-only access to the help-center snapshot). Absolute paths
outside the workspace and `..` escapes are refused — the same guarantee
`tests/unit/test_file_scope.py` asserts.

Tools are built per request as closures bound to that request's workdir, so two
concurrent users can never address each other's files.
"""

from pathlib import Path

from langchain_core.tools import StructuredTool

# Cap returned file content so a single read can't dump a large file into the
# context window (input-cost control). The agent is instructed (system prompt) to
# compute over ./data/*.json with code rather than reading whole data files; help
# articles are short and fit comfortably. ~24 KB ≈ a few thousand tokens.
_MAX_READ_BYTES = 24_000


class PathOutsideWorkspace(Exception):
    """Raised when a tool path resolves outside the allowed roots."""


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _resolve(path: str, workdir: Path, read_roots: list[Path], *, writing: bool) -> Path:
    """Resolve a model-supplied path to an absolute path and enforce confinement.

    Accepts './rel', 'rel', or an absolute path that already sits inside an
    allowed root. Writes are confined to the workspace; reads may also hit the
    read-only roots (the help snapshot)."""
    raw = path.strip()
    # Tolerate an absolute path pointing inside the workspace (the model
    # sometimes emits the full path); reduce it to workspace-relative.
    if raw.startswith(str(workdir)):
        raw = raw[len(str(workdir)):]
    candidate = Path(raw)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (workdir / raw.lstrip("/").removeprefix("./")).resolve()

    allowed = (
        [workdir.resolve()]
        if writing
        else [workdir.resolve(), *(r.resolve() for r in read_roots)]
    )
    if not any(_is_within(resolved, root) for root in allowed):
        raise PathOutsideWorkspace(
            f"path {path!r} is outside your workspace — use a ./-relative path inside it"
        )
    return resolved


def make_file_tools(workdir: Path, read_roots: list[Path]) -> list[StructuredTool]:
    """Return [read_file, write_file, edit_file] confined to `workdir`."""

    def read_file(path: str) -> str:
        """Read a UTF-8 text file from your workspace (or the ./help snapshot).
        Use a ./-relative path, e.g. './help/INDEX.md' or './data/sessions_p1.json'.

        Args:
            path: ./-relative path to the file to read.
        """
        try:
            target = _resolve(path, workdir, read_roots, writing=False)
        except PathOutsideWorkspace as e:
            return f"DENIED: {e}"
        if not target.is_file():
            return f"NOT FOUND: {path}"
        data = target.read_text(encoding="utf-8", errors="replace")
        if len(data) > _MAX_READ_BYTES:
            return (
                data[:_MAX_READ_BYTES]
                + f"\n\n[truncated at {_MAX_READ_BYTES} bytes — query large data files "
                "with code instead of reading them whole]"
            )
        return data

    def write_file(path: str, content: str) -> str:
        """Write (creating or overwriting) a text file in your workspace. Parent
        folders are created as needed. Use a ./-relative path that starts with
        './', e.g. './score-trends/artifact.html'. Writes outside your workspace
        are denied.

        Args:
            path: ./-relative destination path inside your workspace.
            content: Full file contents to write.
        """
        try:
            target = _resolve(path, workdir, read_roots, writing=True)
        except PathOutsideWorkspace as e:
            return f"DENIED: {e}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"wrote {len(content)} chars to {path}"

    def edit_file(path: str, old_string: str, new_string: str) -> str:
        """Replace the first exact occurrence of `old_string` with `new_string`
        in an existing workspace file. Use this to iterate on an artifact —
        change only what was asked, don't rewrite the whole file.

        Args:
            path: ./-relative path to the file to edit.
            old_string: Exact text to find.
            new_string: Replacement text.
        """
        try:
            target = _resolve(path, workdir, read_roots, writing=True)
        except PathOutsideWorkspace as e:
            return f"DENIED: {e}"
        if not target.is_file():
            return f"NOT FOUND: {path}"
        data = target.read_text(encoding="utf-8")
        if old_string not in data:
            return f"NO MATCH: old_string not found in {path}"
        target.write_text(data.replace(old_string, new_string, 1), encoding="utf-8")
        return f"edited {path}"

    return [
        StructuredTool.from_function(read_file),
        StructuredTool.from_function(write_file),
        StructuredTool.from_function(edit_file),
    ]
