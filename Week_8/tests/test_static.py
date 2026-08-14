"""Tests for the AST analyser.

Each rule gets a positive case (it fires) and, where the distinction matters,
a negative case (it does not fire on safe code). A linter that cannot prove it
avoids false positives is not worth running.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auditor.static import analyse_source
from auditor.models import Severity


def rules(source: str, path: str = "sample.py") -> list[str]:
    findings, _ = analyse_source(path, source)
    return [f.rule for f in findings]


def test_eval_is_critical():
    findings, _ = analyse_source("s.py", "result = eval(user_input)\n")
    assert findings[0].rule == "PY-EVAL"
    assert findings[0].severity is Severity.CRITICAL


def test_shell_true_detected_and_safe_call_is_not():
    assert "PY-SHELL-TRUE" in rules("import subprocess\nsubprocess.run(cmd, shell=True)\n")
    assert "PY-SHELL-TRUE" not in rules("import subprocess\nsubprocess.run(['ls', '-l'])\n")


def test_hardcoded_secret_detected_but_placeholder_ignored():
    assert "PY-HARDCODED-SECRET" in rules('api_key = "sk_live_9f3bQ2xZ"\n')
    assert "PY-HARDCODED-SECRET" not in rules('api_key = "changeme"\n')
    # Reading from the environment is the correct pattern and must stay silent.
    assert "PY-HARDCODED-SECRET" not in rules('import os\napi_key = os.getenv("API_KEY")\n')


def test_yaml_load_safe_loader_is_accepted():
    assert "PY-YAML-LOAD" in rules("import yaml\nyaml.load(f)\n")
    assert "PY-YAML-LOAD" not in rules("import yaml\nyaml.load(f, Loader=yaml.SafeLoader)\n")


def test_requests_timeout_rule():
    assert "PY-NO-TIMEOUT" in rules("import requests\nrequests.get(url)\n")
    assert "PY-NO-TIMEOUT" not in rules("import requests\nrequests.get(url, timeout=5)\n")


def test_except_variants_are_distinguished():
    assert "PY-SILENT-EXCEPT" in rules("try:\n    f()\nexcept:\n    pass\n")
    assert "PY-BARE-EXCEPT" in rules("try:\n    f()\nexcept:\n    log()\n")
    assert "PY-SWALLOWED-EXCEPT" in rules("try:\n    f()\nexcept ValueError:\n    pass\n")


def test_mutable_default_argument():
    assert "PY-MUTABLE-DEFAULT" in rules("def f(items=[]):\n    return items\n")
    assert "PY-MUTABLE-DEFAULT" not in rules("def f(items=None):\n    return items or []\n")


def test_string_containing_eval_is_not_flagged():
    """The whole point of using an AST rather than regex."""
    assert "PY-EVAL" not in rules('note = "never call eval(x) here"\n')
    assert "PY-EVAL" not in rules('# eval(x) would be bad\n')


def test_asserts_ignored_in_test_files():
    assert "PY-ASSERT" in rules("assert x == 1\n", path="app/logic.py")
    assert "PY-ASSERT" not in rules("assert x == 1\n", path="tests/test_thing.py")


def test_syntax_error_is_reported_not_raised():
    findings, _ = analyse_source("broken.py", "def oops(:\n")
    assert findings[0].rule == "PY-SYNTAX"
