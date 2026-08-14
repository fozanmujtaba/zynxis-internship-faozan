"""
Week 8 — Capstone: GitHub Code Auditor
A production-shaped agentic pipeline that audits a Python repository.

  discover ─► static analysis ─► secret scan ─► LLM review ─► summary ─► report
   (code)        (AST)             (regex+       (targeted)   (LLM)
                                    entropy)

Deterministic stages run first and always. The LLM reviews only the files that
already look risky, and the whole run degrades to a static-only report if the
model is unreachable.

Run modes:
  python audit.py                        → audit this repository
  python audit.py --path ../Week_6       → audit a specific directory
  python audit.py --no-llm               → deterministic stages only
  python audit.py --max-review 8         → how many files get an LLM review
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from auditor import discover, report, review, secrets, static
from auditor.llm import LLMClient, LLMUnavailable
from auditor.models import AuditResult, Severity

REPORT_MD = "audit_report.md"
FINDINGS_JSON = "audit_findings.json"

BOLD, CYAN, GREEN, YELLOW, RED, DIM, RESET = (
    "\033[1m", "\033[96m", "\033[92m", "\033[93m", "\033[91m", "\033[2m", "\033[0m")

SEVERITY_COLOUR = {
    Severity.CRITICAL: RED, Severity.HIGH: RED, Severity.MEDIUM: YELLOW,
    Severity.LOW: CYAN, Severity.INFO: DIM,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Agentic code auditor.")
    parser.add_argument("--path", default="..", help="repository root to audit")
    parser.add_argument("--no-llm", action="store_true",
                        help="deterministic stages only, zero API calls")
    parser.add_argument("--no-cache", action="store_true", help="bypass the response cache")
    parser.add_argument("--max-review", type=int, default=6,
                        help="how many files receive an LLM review (default: 6)")
    parser.add_argument("--out", default=REPORT_MD, help=f"report path (default: {REPORT_MD})")
    args = parser.parse_args()

    root = Path(args.path).resolve()
    print(f"\n{BOLD}Code Auditor — Week 8 Capstone{RESET}")
    print("=" * 72)
    print(f"Repository : {root}")
    print("=" * 72)

    # -- 1. discovery
    print(f"\n{BOLD}[1/5]{RESET} Discovering source files…")
    try:
        paths, skipped = discover.discover(str(root), extensions=(".py",))
    except FileNotFoundError as exc:
        sys.exit(f"{RED}{exc}{RESET}")

    if not paths:
        sys.exit(f"{YELLOW}No Python files found under {root}{RESET}")

    sources: dict[str, str] = {}
    for path in paths:
        text = discover.read_text(path)
        if text is None:
            skipped.append(f"{path.name}: could not be decoded as UTF-8")
            continue
        sources[str(path.relative_to(root))] = text

    total_lines = sum(len(s.splitlines()) for s in sources.values())
    print(f"{GREEN}  {len(sources)} files · {total_lines:,} lines"
          f"{f' · {len(skipped)} skipped' if skipped else ''}{RESET}")

    result = AuditResult(repo=str(root), files_scanned=len(sources),
                         lines_scanned=total_lines, skipped=skipped)

    # Credential findings inside a test suite are fixtures by design. The
    # policy lives here, applied identically to the AST rule and the secret
    # scanner, and every suppression is recorded so the report can show them.
    CREDENTIAL_RULES = {"PY-HARDCODED-SECRET"}

    def keep(rel: str, finding) -> bool:
        if static.is_test_path(rel) and finding.rule in CREDENTIAL_RULES:
            result.suppressed.append(f"{finding.location} — {finding.title} (test fixture)")
            return False
        return True

    # -- 2. static analysis
    print(f"\n{BOLD}[2/5]{RESET} Static analysis (AST)…")
    for rel, text in sources.items():
        findings, _ = static.analyse_source(rel, text)
        result.findings.extend(f for f in findings if keep(rel, f))
    print(f"{GREEN}  {len(result.findings)} finding(s){RESET}")

    # -- 3. secret scan
    print(f"\n{BOLD}[3/5]{RESET} Secret scan (patterns + entropy)…")
    before = len(result.findings)
    for rel, text in sources.items():
        found = secrets.scan_text(rel, text)
        # Test suites legitimately contain fake credentials as fixtures. They
        # are suppressed rather than dropped: the count is reported, so the
        # decision stays auditable instead of silently shrinking the findings.
        if static.is_test_path(rel):
            for f in found:
                result.suppressed.append(f"{f.location} — {f.title} (test fixture)")
            continue
        result.findings.extend(found)
    print(f"{GREEN}  {len(result.findings) - before} finding(s)"
          f"{f' · {len(result.suppressed)} suppressed in test files' if result.suppressed else ''}{RESET}")

    # -- 4. LLM review of the riskiest files
    summary_md = ""
    if args.no_llm:
        print(f"\n{BOLD}[4/5]{RESET} Skipping LLM review (--no-llm)")
        result.llm_available = False
    else:
        print(f"\n{BOLD}[4/5]{RESET} LLM review of the highest-risk files…")
        sizes = {rel: len(text) for rel, text in sources.items()}
        targets = review.select_for_review(
            list(sources), result.findings, sizes, args.max_review)

        try:
            client = LLMClient(use_cache=not args.no_cache)
            for i, rel in enumerate(targets, start=1):
                print(f"  [{i}/{len(targets)}] {rel}")
                try:
                    found = review.review_file(client, rel, sources[rel])
                except LLMUnavailable as exc:
                    print(f"{YELLOW}  LLM review stopped: {exc}{RESET}")
                    result.llm_available = False
                    break
                result.findings.extend(found)

            result.token_usage = client.usage()

            if result.llm_available:
                print(f"\n{BOLD}[5/5]{RESET} Writing the executive summary…")
                try:
                    summary_md = review.write_summary(
                        client, result.repo, result.sorted_findings(),
                        result.files_scanned, result.lines_scanned,
                        result.counts(), result.by_source())
                except LLMUnavailable as exc:
                    print(f"{YELLOW}  summary unavailable: {exc}{RESET}")
                result.token_usage = client.usage()

        except LLMUnavailable as exc:
            print(f"{YELLOW}  {exc}{RESET}")
            print(f"{YELLOW}  continuing with deterministic findings only{RESET}")
            result.llm_available = False

    if args.no_llm or not result.llm_available:
        print(f"\n{BOLD}[5/5]{RESET} Writing the report…")

    # -- output
    markdown = report.render(result, summary_md)
    Path(args.out).write_text(markdown, encoding="utf-8")
    Path(FINDINGS_JSON).write_text(json.dumps({
        "repo": result.repo,
        "files_scanned": result.files_scanned,
        "lines_scanned": result.lines_scanned,
        "counts": result.counts(),
        "by_source": result.by_source(),
        "token_usage": result.token_usage,
        "llm_available": result.llm_available,
        "findings": [f.to_dict() for f in result.sorted_findings()],
    }, indent=2), encoding="utf-8")

    # -- console digest
    print(f"\n{BOLD}{'=' * 72}{RESET}")
    counts = result.counts()
    for sev in Severity:
        if counts[sev.value]:
            print(f"  {SEVERITY_COLOUR[sev]}{sev.value.upper():<9}{RESET} "
                  f"{counts[sev.value]}")

    top = [f for f in result.sorted_findings()
           if f.severity in (Severity.CRITICAL, Severity.HIGH)][:8]
    if top:
        print(f"\n{BOLD}Most serious:{RESET}")
        for f in top:
            print(f"  {SEVERITY_COLOUR[f.severity]}{f.severity.value.upper():<9}{RESET}"
                  f"{f.title}  {CYAN}{f.location}{RESET}")

    if result.token_usage:
        u = result.token_usage
        print(f"\n{DIM}LLM: {u['api_calls']} calls · {u['cache_hits']} cache hits · "
              f"{u['retries']} retries · {u['total_tokens']:,} tokens{RESET}")

    print(f"\n{GREEN}Done.{RESET} {len(result.findings)} finding(s) across "
          f"{result.files_scanned} files")
    print(f"  {args.out:<22} the report")
    print(f"  {FINDINGS_JSON:<22} structured findings")
    pdf = args.out.rsplit(".", 1)[0] + ".pdf"
    print(f"\n{CYAN}Next:{RESET} python generate_report.py {args.out} {pdf}")


if __name__ == "__main__":
    main()
