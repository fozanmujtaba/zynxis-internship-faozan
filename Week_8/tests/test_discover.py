"""Tests for discovery — the part that decides what never gets read."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auditor.discover import discover


def test_skips_venv_and_pycache(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("x = 1\n")
    for junk in ("venv", "__pycache__", "node_modules"):
        (tmp_path / junk).mkdir()
        (tmp_path / junk / "junk.py").write_text("y = 2\n")

    found, _ = discover(str(tmp_path), extensions=(".py",))
    names = {p.name for p in found}
    assert names == {"main.py"}


def test_skips_oversized_files(tmp_path):
    (tmp_path / "big.py").write_text("# pad\n" * 100_000)
    (tmp_path / "small.py").write_text("x = 1\n")
    found, skipped = discover(str(tmp_path), extensions=(".py",))
    assert {p.name for p in found} == {"small.py"}
    assert any("big.py" in s for s in skipped)
