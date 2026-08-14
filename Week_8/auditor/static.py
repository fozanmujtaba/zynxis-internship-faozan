"""
AST-based static analysis for Python source.

Regex-based linting produces false positives on anything inside a string or a
comment, and misses anything spread across lines. Walking the syntax tree
instead means a finding is proven by the structure of the code: when this
module reports `shell=True`, that keyword genuinely reaches a subprocess call.

Each rule is small and independent so it can be tested in isolation — see
tests/test_static.py.
"""

from __future__ import annotations

import ast
import re

from .models import Finding, Severity, Source
from .secrets import shannon_entropy

# A lowercase slug — "secret-scan", "api_key_header" — is a label, not a
# credential. Enum members and dict keys trip the name check constantly, and
# flagging them buries the real findings.
SLUG = re.compile(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*\Z")

# Names that, when assigned a string literal, indicate a credential in source.
SECRET_NAMES = (
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "access_key", "private_key", "credential", "auth_token",
)

# Hashes that are unfit for password storage.
WEAK_HASHES = {"md5", "sha1"}


def _name_of(node: ast.AST) -> str:
    """Dotted name for a call target: subprocess.run -> 'subprocess.run'."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name_of(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _keyword(call: ast.Call, name: str) -> ast.AST | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _is_true(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


class Analyzer(ast.NodeVisitor):
    def __init__(self, path: str, lines: list[str]):
        self.path = path
        self.lines = lines
        self.findings: list[Finding] = []

    # -- helpers ------------------------------------------------------

    def _snippet(self, line: int) -> str:
        if 1 <= line <= len(self.lines):
            return self.lines[line - 1].strip()[:160]
        return ""

    def _add(self, rule: str, severity: Severity, title: str, detail: str,
             node: ast.AST, remediation: str, confidence: str = "confirmed") -> None:
        line = getattr(node, "lineno", 0)
        self.findings.append(Finding(
            rule=rule, severity=severity, title=title, detail=detail,
            path=self.path, line=line, source=Source.AST,
            snippet=self._snippet(line), remediation=remediation,
            confidence=confidence,
        ))

    # -- rules --------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        name = _name_of(node.func)

        if name in ("eval", "exec"):
            self._add(
                "PY-EVAL", Severity.CRITICAL, f"Use of {name}()",
                f"{name}() executes arbitrary code. If any part of its argument "
                "can be influenced by user input, this is remote code execution.",
                node, f"Replace {name}() with explicit parsing — ast.literal_eval "
                "for data, or a dispatch dict for behaviour.")

        if name == "os.system":
            self._add(
                "PY-OS-SYSTEM", Severity.HIGH, "Use of os.system()",
                "os.system() passes its argument to a shell, so any interpolated "
                "value can inject further commands.",
                node, "Use subprocess.run([...]) with an argument list and no shell.")

        if name in ("subprocess.run", "subprocess.call", "subprocess.Popen",
                    "subprocess.check_call", "subprocess.check_output"):
            if _is_true(_keyword(node, "shell")):
                self._add(
                    "PY-SHELL-TRUE", Severity.HIGH, "subprocess called with shell=True",
                    "shell=True runs the command through a shell, making any "
                    "interpolated value a command-injection vector.",
                    node, "Pass the command as a list and drop shell=True.")

        if name in ("pickle.load", "pickle.loads"):
            self._add(
                "PY-PICKLE", Severity.HIGH, "Deserialising with pickle",
                "pickle executes arbitrary code during deserialisation, so "
                "untrusted input is equivalent to running it.",
                node, "Use JSON for untrusted data, or verify the payload's "
                "provenance before unpickling.")

        if name in ("yaml.load",) and not _keyword(node, "Loader"):
            self._add(
                "PY-YAML-LOAD", Severity.HIGH, "yaml.load() without a safe Loader",
                "The default loader can construct arbitrary Python objects.",
                node, "Use yaml.safe_load(), or pass Loader=yaml.SafeLoader.")

        if name in ("hashlib.md5", "hashlib.sha1"):
            self._add(
                "PY-WEAK-HASH", Severity.MEDIUM, f"Weak hash: {name}",
                "MD5 and SHA-1 are collision-prone and far too fast for password "
                "hashing.",
                node, "Use hashlib.sha256 for integrity, or bcrypt/argon2 for "
                "passwords.", confidence="probable")

        if name == "tempfile.mktemp":
            self._add(
                "PY-MKTEMP", Severity.MEDIUM, "tempfile.mktemp() is race-prone",
                "The returned path can be created by another process between the "
                "call and your open().",
                node, "Use tempfile.mkstemp() or NamedTemporaryFile().")

        # Network calls with no timeout hang forever when the peer stalls.
        if name.startswith("requests.") and name.split(".")[-1] in (
                "get", "post", "put", "patch", "delete", "head", "request"):
            if _keyword(node, "timeout") is None:
                self._add(
                    "PY-NO-TIMEOUT", Severity.MEDIUM, "HTTP request without a timeout",
                    "requests has no default timeout, so a stalled peer blocks the "
                    "calling thread indefinitely.",
                    node, "Pass timeout=<seconds> to every request.")

        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Hardcoded credentials: NAME = "literal"
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            value = node.value.value
            for target in node.targets:
                ident = _name_of(target).lower()
                if any(s in ident for s in SECRET_NAMES) and len(value) >= 6:
                    # Placeholders and env lookups are not real credentials.
                    if value.lower() in ("changeme", "password", "your_key_here",
                                         "xxx", "todo", "none", "null", ""):
                        continue
                    # A lowercase slug is a label — enum members and config
                    # keys otherwise dominate this rule's output.
                    if SLUG.match(value):
                        continue
                    # Real credentials are high-entropy; prose and identifiers
                    # are not.
                    if shannon_entropy(value) < 2.5:
                        continue
                    self._add(
                        "PY-HARDCODED-SECRET", Severity.CRITICAL,
                        "Hardcoded credential in source",
                        f"'{ident}' is assigned a string literal. Anything committed "
                        "to git is permanently in the history, even if later removed.",
                        node, "Read it from an environment variable or a secret "
                        "manager, then rotate the exposed value.")
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        swallowed = all(isinstance(s, ast.Pass) for s in node.body)
        bare = node.type is None

        if bare and swallowed:
            self._add(
                "PY-SILENT-EXCEPT", Severity.MEDIUM, "Bare except that swallows everything",
                "This catches SystemExit and KeyboardInterrupt too, and discards "
                "the error, so failures become silent.",
                node, "Catch the specific exception you expect, and log it.")
        elif bare:
            self._add(
                "PY-BARE-EXCEPT", Severity.LOW, "Bare except clause",
                "A bare except also catches SystemExit and KeyboardInterrupt.",
                node, "Use `except Exception:` at minimum, ideally something narrower.")
        elif swallowed:
            self._add(
                "PY-SWALLOWED-EXCEPT", Severity.LOW, "Exception caught and discarded",
                "The handler body is just `pass`, so the failure leaves no trace.",
                node, "Log the exception, even if recovery is genuinely a no-op.")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Mutable default arguments persist across calls.
        for default in node.args.defaults + [d for d in node.args.kw_defaults if d]:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                self._add(
                    "PY-MUTABLE-DEFAULT", Severity.MEDIUM,
                    f"Mutable default argument in {node.name}()",
                    "The default object is created once at definition time and "
                    "shared by every call, so mutations leak between calls.",
                    node, "Default to None and build the container inside the body.")
                break
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Assert(self, node: ast.Assert) -> None:
        self._add(
            "PY-ASSERT", Severity.LOW, "assert used outside a test",
            "Assertions are removed when Python runs with -O, so any validation "
            "they perform silently disappears in optimised deployments.",
            node, "Raise an explicit exception for runtime validation.",
            confidence="advisory")
        self.generic_visit(node)


def analyse_source(path: str, source: str) -> tuple[list[Finding], int]:
    """Runs every rule over one file. Returns (findings, line count).

    A file that does not parse yields a finding rather than an exception: an
    auditor that dies on one bad file is useless on a real repository.
    """
    lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return ([Finding(
            rule="PY-SYNTAX", severity=Severity.INFO,
            title="File could not be parsed",
            detail=f"SyntaxError: {exc.msg} (line {exc.lineno}). Skipped by the "
                   "static analyser; it may target a different Python version.",
            path=path, line=exc.lineno or 0, source=Source.AST,
            remediation="Confirm the file is valid for the interpreter in use.",
            confidence="confirmed")], len(lines))

    # Tests legitimately use assert; reporting them would bury the real findings.
    analyzer = Analyzer(path, lines)
    analyzer.visit(tree)
    findings = analyzer.findings
    if is_test_path(path):
        findings = [f for f in findings if f.rule != "PY-ASSERT"]
    return findings, len(lines)


def is_test_path(path: str) -> bool:
    lowered = path.replace("\\", "/").lower()
    return (
        "/tests/" in lowered
        or lowered.startswith("tests/")
        or lowered.rsplit("/", 1)[-1].startswith("test_")
        or lowered.endswith("_test.py")
    )
