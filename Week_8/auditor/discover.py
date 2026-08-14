"""Repository walking and file selection.

Deciding what *not* to read is most of the work: a venv or a node_modules
directory will happily supply a hundred thousand files of other people's code
and drown every real finding.
"""

from __future__ import annotations

import os
from pathlib import Path

SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "venv", ".venv", "env", "node_modules", "dist", "build",
    ".next", ".tox", "site-packages", ".idea", ".vscode", "vendor",
    "chroma_store", ".eggs",
}

SKIP_SUFFIXES = {
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe", ".bin", ".lock",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf", ".zip",
    ".gz", ".tar", ".whl", ".woff", ".woff2", ".ttf", ".mp4", ".xml",
}

# Files above this are almost always generated or vendored.
MAX_BYTES = 400_000


def is_probably_binary(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return b"\0" in f.read(2048)
    except OSError:
        return True


def discover(root: str, extensions: tuple[str, ...] = (".py",)) -> tuple[list[Path], list[str]]:
    """Returns (files worth auditing, human-readable reasons for skipping)."""
    root_path = Path(root).resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"no such path: {root}")

    selected: list[Path] = []
    skipped: list[str] = []

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Pruning in place stops os.walk descending into them at all.
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS
                             and not d.startswith("."))

        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            rel = str(path.relative_to(root_path))

            if path.suffix.lower() in SKIP_SUFFIXES:
                continue
            if extensions and path.suffix.lower() not in extensions:
                continue

            try:
                size = path.stat().st_size
            except OSError:
                continue

            if size == 0:
                continue
            if size > MAX_BYTES:
                skipped.append(f"{rel}: {size // 1024}KB exceeds the {MAX_BYTES // 1024}KB cap")
                continue
            if is_probably_binary(path):
                skipped.append(f"{rel}: appears to be binary")
                continue

            selected.append(path)

    return selected, skipped


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None
