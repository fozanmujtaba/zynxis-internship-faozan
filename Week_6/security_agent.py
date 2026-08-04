"""
Week 6 — Agentic Cybersecurity
A Security Analyst agent that scans a host with nmap, triages the results
against a deterministic rules engine, and has an LLM turn that evidence into a
prioritised security report.

    nmap  ──►  parse  ──►  rules engine  ──►  LLM analyst  ──►  report
                              (grounding)      (judgement)

Run modes:
  python security_agent.py                          → scan scanme.nmap.org
  python security_agent.py --profile standard       → wider port range
  python security_agent.py --xml sample_scan.xml    → re-analyse a saved scan
  python security_agent.py --xml ... --no-llm       → rules only, zero API calls
  python security_agent.py --target host --authorised

Only scan hosts you own or are authorised to test.
"""

from __future__ import annotations

import argparse
import json
import sys

import rules
import scan as scanner

REPORT_MD    = "security_report.md"
FINDINGS_JSON = "findings.json"
SCAN_XML     = "scan.xml"

BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
RESET  = "\033[0m"

SEVERITY_COLOUR = {
    "critical": RED,
    "high":     RED,
    "medium":   YELLOW,
    "low":      CYAN,
    "info":     RESET,
}


def print_findings(findings: list[dict]) -> None:
    if not findings:
        print(f"  {GREEN}no rule findings{RESET}")
        return
    for f in findings:
        colour = SEVERITY_COLOUR[f["severity"]]
        target = f["host"] + (f":{f['port']}" if f["port"] else "")
        print(f"  {colour}{f['severity'].upper():<9}{RESET} {f['title']}  {CYAN}{target}{RESET}")


def build_header(scan_data: dict, findings: list[dict], target: str, llm_used: bool) -> str:
    counts = rules.severity_counts(findings)
    counts_line = " · ".join(f"{k}: {v}" for k, v in counts.items() if v) or "none"
    return "\n".join([
        "# Network Security Assessment",
        "",
        f"**Target:** {target}  ",
        f"**Scanned:** {scan_data['scanned_at']}  ",
        f"**Nmap invocation:** `{scan_data.get('nmap_args', 'n/a')}`  ",
        f"**Hosts up:** {scan_data['host_count']}  ",
        f"**Rule-engine findings:** {counts_line}  ",
        f"**Analyst:** {'llama-3.3-70b-versatile (Groq)' if llm_used else 'rules engine only (--no-llm)'}  ",
        "**Prepared by:** Faozan Mujtaba — Zynxis Agentic AI Internship, Week 6",
        "",
        "> This assessment covers an authorised scan only. Version-based findings are "
        "inferred from service banners and require verification against vendor "
        "advisories before being treated as confirmed vulnerabilities.",
        "",
        "---",
        "",
    ])


def rules_only_report(findings: list[dict]) -> str:
    """The fallback write-up when the LLM analyst is skipped."""
    if not findings:
        return "## Findings\n\nThe rules engine produced no findings for this scan.\n"

    lines = ["## Findings\n",
             "| Severity | Finding | Host | Port | Rationale |",
             "| --- | --- | --- | --- | --- |"]
    for f in findings:
        lines.append(
            f"| {f['severity'].upper()} | {f['title']} | {f['host']} "
            f"| {f['port'] or '—'} | {f['rationale']} |"
        )
    lines += ["", "## Evidence\n", "```", rules.format_findings(findings), "```", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Nmap-driven security analyst agent.")
    parser.add_argument("--target", default="scanme.nmap.org", help="host to scan")
    parser.add_argument("--profile", default="quick", choices=sorted(scanner.PROFILES),
                        help="nmap scan profile (default: quick)")
    parser.add_argument("--xml", help="analyse an existing nmap XML file instead of scanning")
    parser.add_argument("--no-llm", action="store_true",
                        help="run the rules engine only, making zero API calls")
    parser.add_argument("--authorised", action="store_true",
                        help="assert you own or are authorised to test --target")
    parser.add_argument("--out", default=REPORT_MD,
                        help=f"where to write the assessment (default: {REPORT_MD})")
    args = parser.parse_args()

    findings_json = (args.out.rsplit(".", 1)[0] + "_findings.json"
                     if args.out != REPORT_MD else FINDINGS_JSON)

    print(f"\n{BOLD}Security Analyst Agent — Week 6{RESET}")
    print("=" * 68)

    # 1. Obtain a scan, either fresh or from disk.
    try:
        if args.xml:
            print(f"{BOLD}[1/4]{RESET} Loading saved scan: {args.xml}")
            with open(args.xml, encoding="utf-8") as f:
                xml_text = f.read()
            source = args.xml
        else:
            print(f"{BOLD}[1/4]{RESET} Scanning {args.target} (profile: {args.profile})")
            scanner.check_authorised(args.target, args.authorised)
            xml_text = scanner.run_nmap(args.target, args.profile, SCAN_XML)
            source = args.target

        scan_data = scanner.parse_scan(xml_text)
    except (scanner.ScanError, OSError) as exc:
        sys.exit(f"{RED}{exc}{RESET}")

    print(f"{BOLD}[2/4]{RESET} Parsed scan")
    print(scanner.summarise(scan_data))

    # 2. Ground the analysis in deterministic rules before involving the model.
    print(f"\n{BOLD}[3/4]{RESET} Rules engine triage")
    findings = rules.analyse(scan_data)
    print_findings(findings)

    with open(findings_json, "w", encoding="utf-8") as f:
        json.dump({"scan": scan_data, "findings": findings}, f, indent=2)

    # 3. Hand the evidence to the analyst.
    if args.no_llm:
        print(f"\n{BOLD}[4/4]{RESET} Skipping LLM analyst (--no-llm)")
        body = rules_only_report(findings)
    else:
        print(f"\n{BOLD}[4/4]{RESET} LLM analyst writing the assessment…")
        try:
            import analyst
            body = analyst.analyse(scan_data, findings, scanner.summarise(scan_data))
        except Exception as exc:
            print(f"{RED}  analyst unavailable: {exc}{RESET}")
            print(f"{YELLOW}  falling back to the rules-only report{RESET}")
            body = rules_only_report(findings)
            args.no_llm = True

    report = build_header(scan_data, findings, source, llm_used=not args.no_llm) + body
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(report.rstrip() + "\n")

    print(f"\n{BOLD}{'=' * 68}{RESET}")
    print(f"{GREEN}Done.{RESET} {len(findings)} finding(s) across {scan_data['host_count']} host(s)")
    print(f"  {args.out:<22} the assessment")
    print(f"  {findings_json:<22} structured scan + findings")
    if not args.xml:
        print(f"  {SCAN_XML:<22} raw nmap XML")
    pdf = args.out.rsplit(".", 1)[0] + ".pdf"
    print(f"\n{CYAN}Next:{RESET} python generate_report.py {args.out} {pdf}")


if __name__ == "__main__":
    main()
