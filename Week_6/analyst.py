"""
Week 6 — The LLM half of the Security Analyst agent.

The rules engine has already decided *what* is wrong. This module asks the
model to do the part rules are bad at: judge how much it matters on this
particular host, connect findings that are individually minor but dangerous
together, and say what to fix first.

The prompt is deliberately strict about not inventing CVE numbers. A security
report that cites a plausible-looking CVE that does not exist is worse than
one that cites none.
"""

from __future__ import annotations

import os

from groq import Groq
from dotenv import load_dotenv

from rules import format_findings, severity_counts

load_dotenv()

MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """\
You are a senior security analyst writing the findings section of a network
assessment. You are given the output of an authorised nmap scan and a set of
findings that a deterministic rules engine has already confirmed.

Rules you must follow:

- Ground every statement in the scan evidence you were given. Do not speculate
  about services, ports or software that are not in the scan.
- Never invent CVE identifiers. Name a CVE only if you are confident it is
  real and applies; otherwise describe the vulnerability class in words. It is
  correct and expected to say "verify against the vendor advisory".
- Version-based findings are inferences from a service banner, not proof of
  exploitability. Say so.
- Prioritise ruthlessly. An analyst who marks everything critical is useless.
- Be concrete about remediation: the specific config change, not "harden it".

Write in markdown. Do not open with a preamble about what you were asked to do.\
"""

REPORT_TEMPLATE = """\
Produce the analyst write-up for this scan.

## SCAN EVIDENCE

Nmap invocation: {args}
Hosts up: {host_count}

{digest}

## CONFIRMED RULE-ENGINE FINDINGS

Severity counts: {counts}

{findings}

## REQUIRED STRUCTURE

Write these sections, in this order, with these exact headings:

## Executive Summary
Three to five sentences: the overall exposure of what was scanned, the single
most urgent issue, and whether this host looks intentionally public or
accidentally exposed.

## Risk Assessment by Host
For each host, a short paragraph judging its overall posture, then a markdown
table with columns: Severity | Finding | Port | Why it matters.

## Suspicious Indicators
Anything that suggests misconfiguration, compromise, or a service that has no
business being reachable. If the host looks clean and deliberate, say that
plainly instead of manufacturing suspicion.

## Likely Vulnerabilities
Vulnerability classes implied by the detected software and versions. Mark each
as CONFIRMED (proven by the scan itself) or REQUIRES VERIFICATION (inferred
from a version banner).

## Prioritised Remediation
A numbered list, most urgent first. Each item: the action, the host and port it
applies to, and the effort involved (low/medium/high).
"""


def build_client() -> Groq:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set — add it to Week_6/.env")
    return Groq(api_key=key)


def analyse(scan: dict, findings: list[dict], digest: str) -> str:
    """Asks the model to turn scan evidence + rule findings into a report."""
    counts = severity_counts(findings)
    counts_line = ", ".join(f"{k}={v}" for k, v in counts.items() if v)

    prompt = REPORT_TEMPLATE.format(
        args=scan.get("nmap_args", "n/a"),
        host_count=scan.get("host_count", 0),
        digest=digest,
        counts=counts_line or "none",
        findings=format_findings(findings),
    )

    client = build_client()
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,          # low: this is analysis, not prose generation
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content.strip()
