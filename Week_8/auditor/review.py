"""
The LLM review stage.

Two jobs, deliberately separated:

  1. `review_file` looks at high-risk source files for defects the AST rules
     cannot express — logic errors, missing validation, unsafe assumptions.
  2. `write_summary` reads the *whole* finding set and writes the executive
     narrative: what kind of shape this codebase is in, and what to fix first.

Only files the deterministic stages already flagged, plus the largest few, are
sent to the model. Auditing every file with an LLM is how you spend a token
budget producing observations about `__init__.py`.
"""

from __future__ import annotations

import json

from .llm import LLMClient, LLMUnavailable
from .models import Finding, Severity, Source

REVIEW_SYSTEM = """\
You are a staff engineer reviewing a colleague's code before it ships.

Report only defects you can point at in the code shown. Specifically:
correctness bugs, unhandled edge cases, missing input validation, resource
leaks, race conditions, and error handling that hides failure.

Do not report style, formatting, naming, or missing type hints. Do not
speculate about code you cannot see. If the file is genuinely fine, return an
empty findings list — an empty list is a valid and useful answer, and padding
it with invented concerns makes the whole report untrustworthy.

Respond only with JSON.\
"""

REVIEW_USER = """\
Review this file.

PATH: {path}

```python
{source}
```

Return JSON:
{{
  "findings": [
    {{"line": <integer line number>,
      "severity": "critical|high|medium|low",
      "title": "short description of the defect",
      "detail": "what goes wrong, and the conditions under which it happens",
      "remediation": "the specific change that fixes it"}}
  ]
}}

At most {limit} findings, most serious first.\
"""

SUMMARY_SYSTEM = """\
You are a staff engineer writing the executive summary of a code audit for a
team lead who will not read the full findings table.

Be direct about severity without inflating it. If the codebase is in decent
shape, say so. Ground every claim in the findings you were given.

Write markdown. No preamble about what you were asked to do.\
"""

SUMMARY_USER = """\
Write the executive summary for this audit.

REPOSITORY: {repo}
FILES SCANNED: {files} ({lines} lines)
SEVERITY COUNTS: {counts}
FINDINGS BY SOURCE: {sources}

THE FINDINGS:
{findings}

Write these sections with these exact headings:

## Executive Summary
Four to six sentences: the overall health of this codebase, the most serious
issue, and whether the problems look systemic or isolated.

## Themes
The two to four patterns behind the individual findings — what the repeated
issues have in common. If there is no pattern, say the findings are isolated.

## Recommended Priorities
A numbered list of at most five actions, most urgent first. Each names the
specific files or rules it addresses and why it ranks where it does.\
"""

MAX_SOURCE_CHARS = 12_000


def select_for_review(paths: list[str], findings: list[Finding],
                      sizes: dict[str, int], limit: int) -> list[str]:
    """Picks which files justify an LLM call.

    Files the deterministic stages already flagged come first — somewhere with
    one confirmed problem is the likeliest place to find another — then the
    largest remaining files, where complexity concentrates.
    """
    flagged: dict[str, int] = {}
    for f in findings:
        flagged[f.path] = flagged.get(f.path, 0) + (5 - f.severity.rank)

    ranked = sorted(flagged.items(), key=lambda kv: -kv[1])
    chosen = [p for p, _ in ranked][:limit]

    if len(chosen) < limit:
        remaining = sorted(
            (p for p in paths if p not in chosen),
            key=lambda p: -sizes.get(p, 0))
        chosen += remaining[: limit - len(chosen)]

    return chosen


def review_file(client: LLMClient, path: str, source: str,
                limit: int = 5) -> list[Finding]:
    """Asks the model for defects in one file. Never raises on bad output."""
    truncated = source[:MAX_SOURCE_CHARS]
    note = "" if len(source) <= MAX_SOURCE_CHARS else "\n# … file truncated for review"

    raw = client.complete(
        REVIEW_SYSTEM,
        REVIEW_USER.format(path=path, source=truncated + note, limit=limit),
        json_mode=True,
    )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    findings: list[Finding] = []
    for item in (data.get("findings") or [])[:limit]:
        try:
            severity = Severity(str(item.get("severity", "low")).lower())
        except ValueError:
            severity = Severity.LOW

        try:
            line = int(item.get("line", 0) or 0)
        except (TypeError, ValueError):
            line = 0

        title = str(item.get("title", "")).strip()
        if not title:
            continue

        findings.append(Finding(
            rule="LLM-REVIEW", severity=severity, title=title,
            detail=str(item.get("detail", "")).strip(),
            path=path, line=line, source=Source.LLM,
            remediation=str(item.get("remediation", "")).strip(),
            # The model cannot execute the code, so its findings are opinions
            # about it — flagged as such so they are read that way.
            confidence="advisory",
        ))
    return findings


def write_summary(client: LLMClient, repo: str, findings: list[Finding],
                  files: int, lines: int, counts: dict, sources: dict) -> str:
    listing = "\n".join(
        f"- [{f.severity.value.upper()}] {f.rule} {f.location} — {f.title}"
        for f in findings[:60]
    ) or "- no findings"

    return client.complete(
        SUMMARY_SYSTEM,
        SUMMARY_USER.format(
            repo=repo, files=files, lines=lines,
            counts=", ".join(f"{k}={v}" for k, v in counts.items() if v) or "none",
            sources=", ".join(f"{k}={v}" for k, v in sources.items()) or "none",
            findings=listing,
        ),
        temperature=0.3,
    ).strip()
