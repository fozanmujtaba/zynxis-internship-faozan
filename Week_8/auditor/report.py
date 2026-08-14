"""Renders an AuditResult into the markdown report."""

from __future__ import annotations

from datetime import datetime

from .models import AuditResult, Severity, Source

SEVERITY_LABEL = {
    Severity.CRITICAL: "CRITICAL",
    Severity.HIGH: "HIGH",
    Severity.MEDIUM: "MEDIUM",
    Severity.LOW: "LOW",
    Severity.INFO: "INFO",
}

CONFIDENCE_NOTE = {
    "confirmed": "Proven by the syntax tree or an exact pattern match.",
    "probable": "Strong signal, but worth a human glance before acting.",
    "advisory": "The model's opinion; it could not execute the code.",
}


def render(result: AuditResult, summary_md: str = "") -> str:
    counts = result.counts()
    sources = result.by_source()
    findings = result.sorted_findings()

    out: list[str] = [
        "# Code Audit Report",
        "",
        f"**Repository:** {result.repo}  ",
        f"**Audited:** {datetime.now():%d %B %Y, %H:%M}  ",
        f"**Scope:** {result.files_scanned} files · {result.lines_scanned:,} lines  ",
        "**Findings:** "
        + (" · ".join(f"{SEVERITY_LABEL[Severity(k)]}: {v}"
                      for k, v in counts.items() if v) or "none")
        + "  ",
        "**Sources:** "
        + (" · ".join(f"{k}: {v}" for k, v in sorted(sources.items())) or "none")
        + "  ",
    ]

    if result.token_usage:
        u = result.token_usage
        out.append(
            f"**LLM usage:** {u.get('api_calls', 0)} calls · "
            f"{u.get('cache_hits', 0)} cache hits · {u.get('retries', 0)} retries · "
            f"{u.get('total_tokens', 0):,} tokens  ")
    if not result.llm_available:
        out.append("**Note:** the LLM reviewer was unavailable; this report "
                   "contains deterministic findings only.  ")

    out += [
        "",
        "> Findings carry a confidence level. `confirmed` means the analyser "
        "proved it from the syntax tree or an exact credential pattern. "
        "`advisory` means a language model suggested it and could not run the "
        "code. Treat them differently.",
        "",
        "---",
        "",
    ]

    if summary_md:
        out += [summary_md, "", "---", ""]

    # -- severity overview
    out += ["## Findings by Severity", "",
            "| Severity | Count | What it means |", "|---|---|---|"]
    meaning = {
        Severity.CRITICAL: "Exploitable now, or a live credential. Fix before merging.",
        Severity.HIGH: "A serious defect or a dangerous pattern. Fix this sprint.",
        Severity.MEDIUM: "A real problem with a workaround or narrower blast radius.",
        Severity.LOW: "Worth tidying; unlikely to cause an incident alone.",
        Severity.INFO: "Informational — no action implied.",
    }
    for sev in Severity:
        if counts[sev.value]:
            out.append(f"| {SEVERITY_LABEL[sev]} | {counts[sev.value]} | {meaning[sev]} |")
    out += [""]

    # -- the findings themselves
    out += ["## Findings", ""]
    if not findings:
        out += ["No findings. The deterministic analysers found nothing to report.", ""]
    else:
        current = None
        for f in findings:
            if f.severity != current:
                current = f.severity
                out += [f"### {SEVERITY_LABEL[f.severity]}", ""]

            out += [
                f"**{f.rule} — {f.title}**  ",
                f"`{f.location}` · {f.source.value} · confidence: {f.confidence}",
                "",
                f.detail,
                "",
            ]
            if f.snippet:
                out += ["```python", f.snippet, "```", ""]
            if f.remediation:
                out += [f"*Fix:* {f.remediation}", ""]

    # -- rule appendix, so a reader can see what was actually checked
    rules = sorted({f.rule for f in findings})
    if rules:
        out += ["## Rules Triggered", "",
                "| Rule | Occurrences | Confidence |", "|---|---|---|"]
        for rule in rules:
            hits = [f for f in findings if f.rule == rule]
            out.append(f"| {rule} | {len(hits)} | {hits[0].confidence} |")
        out += [""]

    out += ["## Confidence Levels", "",
            "| Level | Meaning |", "|---|---|"]
    for level, note in CONFIDENCE_NOTE.items():
        out.append(f"| {level} | {note} |")
    out += [""]

    if result.suppressed:
        out += ["## Suppressed Findings", "",
                f"{len(result.suppressed)} secret-scan finding(s) inside test "
                "files were suppressed. Test suites carry fake credentials as "
                "fixtures by design; they are listed here so the suppression is "
                "visible rather than silent.", ""]
        out += [f"- {s}" for s in result.suppressed[:15]]
        if len(result.suppressed) > 15:
            out.append(f"- …and {len(result.suppressed) - 15} more")
        out += [""]

    if result.skipped:
        out += ["## Skipped Files", "",
                f"{len(result.skipped)} file(s) were not audited:", ""]
        out += [f"- {s}" for s in result.skipped[:20]]
        if len(result.skipped) > 20:
            out.append(f"- …and {len(result.skipped) - 20} more")
        out += [""]

    return "\n".join(out)
