"""Shared types for the code auditor.

Every finding — whether it came from the AST analyser, the secret scanner or
the LLM reviewer — is the same shape, so downstream code never needs to know
which stage produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def rank(self) -> int:
        return _RANK[self]


_RANK = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


class Source(str, Enum):
    """Which stage produced a finding. Kept on every record because the two
    carry very different warranties: AST findings are proven by the syntax
    tree, LLM findings are opinions worth reading."""
    AST = "static-analysis"
    SECRET = "secret-scan"
    LLM = "llm-review"


@dataclass
class Finding:
    rule: str
    severity: Severity
    title: str
    detail: str
    path: str
    line: int = 0
    source: Source = Source.AST
    snippet: str = ""
    remediation: str = ""
    confidence: str = "confirmed"   # confirmed | probable | advisory

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        d["source"] = self.source.value
        return d

    @property
    def location(self) -> str:
        return f"{self.path}:{self.line}" if self.line else self.path


@dataclass
class AuditResult:
    repo: str
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    lines_scanned: int = 0
    skipped: list[str] = field(default_factory=list)
    llm_available: bool = True
    token_usage: dict = field(default_factory=dict)
    suppressed: list[str] = field(default_factory=list)

    def sorted_findings(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: (f.severity.rank, f.path, f.line))

    def counts(self) -> dict[str, int]:
        counts = {s.value: 0 for s in Severity}
        for f in self.findings:
            counts[f.severity.value] += 1
        return counts

    def by_source(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.findings:
            out[f.source.value] = out.get(f.source.value, 0) + 1
        return out
