"""
Secret detection across any text file.

Two complementary strategies, because each fails where the other works:

  - Provider patterns catch known key shapes (AWS, GitHub, Slack, Stripe…)
    with near-zero false positives, but only for providers we know about.
  - Shannon entropy catches high-randomness strings from providers we don't,
    at the cost of occasionally flagging a hash or a base64 blob.

Entropy findings are therefore marked `probable`, not `confirmed` — the
distinction is carried through to the report so a reviewer knows which ones
deserve doubt.
"""

from __future__ import annotations

import math
import re

from .models import Finding, Severity, Source

PROVIDER_PATTERNS: list[tuple[str, str, str, Severity]] = [
    ("AWS access key id",   r"AKIA[0-9A-Z]{16}",                        "SEC-AWS", Severity.CRITICAL),
    ("GitHub token",        r"gh[pousr]_[A-Za-z0-9]{36,}",              "SEC-GITHUB", Severity.CRITICAL),
    ("Slack token",         r"xox[baprs]-[A-Za-z0-9-]{10,}",            "SEC-SLACK", Severity.CRITICAL),
    ("Stripe secret key",   r"sk_live_[A-Za-z0-9]{16,}",                "SEC-STRIPE", Severity.CRITICAL),
    ("Google API key",      r"AIza[0-9A-Za-z\-_]{35}",                  "SEC-GOOGLE", Severity.HIGH),
    ("OpenAI key",          r"sk-[A-Za-z0-9]{32,}",                     "SEC-OPENAI", Severity.CRITICAL),
    ("Groq key",            r"gsk_[A-Za-z0-9]{40,}",                    "SEC-GROQ", Severity.CRITICAL),
    ("Private key block",   r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----",
                                                                        "SEC-PRIVKEY", Severity.CRITICAL),
    ("JWT",                 r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
                                                                        "SEC-JWT", Severity.HIGH),
    ("Connection string with password",
                            r"(?:postgres|postgresql|mysql|mongodb)(?:\+\w+)?://[^\s:@]+:[^\s:@]+@",
                                                                        "SEC-DBURL", Severity.CRITICAL),
]

# KEY = "value" where the value looks like a credential.
ASSIGNMENT = re.compile(
    r"""(?i)\b(\w*(?:secret|token|password|passwd|api[_-]?key|access[_-]?key)\w*)\s*[:=]\s*['"]([^'"]{8,})['"]"""
)

# Strings that are obviously not live credentials.
PLACEHOLDER = re.compile(
    r"(?i)^(your[_-]|xxx+$|todo|changeme|placeholder|example|dummy|test[_-]?key|"
    r"\$\{|<[^>]+>|\.\.\.|none$|null$)"
)


def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    counts: dict[str, int] = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _is_placeholder(value: str) -> bool:
    return bool(PLACEHOLDER.search(value.strip()))


def scan_text(path: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    lines = text.splitlines()

    for lineno, line in enumerate(lines, start=1):
        if len(line) > 1000:          # minified bundles produce only noise
            continue

        stripped = line.strip()

        for label, pattern, rule, severity in PROVIDER_PATTERNS:
            match = re.search(pattern, line)
            if match:
                findings.append(Finding(
                    rule=rule, severity=severity,
                    title=f"{label} committed to source",
                    detail=f"A string matching the {label} format appears here. "
                           "Credentials in git remain in history after deletion.",
                    path=path, line=lineno, source=Source.SECRET,
                    snippet=_redact(stripped, match.group(0)),
                    remediation="Revoke and rotate the credential, then load it "
                                "from the environment or a secret manager.",
                    confidence="confirmed"))

        m = ASSIGNMENT.search(line)
        if m:
            name, value = m.group(1), m.group(2)
            if not _is_placeholder(value) and shannon_entropy(value) >= 3.0:
                findings.append(Finding(
                    rule="SEC-ASSIGNED", severity=Severity.HIGH,
                    title=f"Credential-shaped assignment to '{name}'",
                    detail=f"'{name}' is set to a high-entropy literal "
                           f"({shannon_entropy(value):.1f} bits/char), which is "
                           "characteristic of a real key rather than a placeholder.",
                    path=path, line=lineno, source=Source.SECRET,
                    snippet=_redact(stripped, value),
                    remediation="Move the value to an environment variable and "
                                "rotate it if it was ever committed.",
                    confidence="probable"))

    return findings


def _redact(line: str, secret: str) -> str:
    """Never reproduce a live credential in a report that gets shared."""
    if len(secret) <= 8:
        masked = "*" * len(secret)
    else:
        masked = f"{secret[:4]}{'*' * 8}{secret[-2:]}"
    return line.replace(secret, masked)[:160]
