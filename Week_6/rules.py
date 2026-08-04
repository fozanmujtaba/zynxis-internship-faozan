"""
Week 6 — Deterministic triage rules.

The LLM analyst is good at explaining and prioritising, and bad at being
consistent about whether port 23 is bad. So the boring, checkable judgements
happen here first, in plain Python, and the model gets handed the resulting
findings as evidence rather than being asked to spot them itself.

This is the difference between an agent that reasons over grounded facts and
one that free-associates about a port list.
"""

from __future__ import annotations

import re

SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]

# Services that carry credentials or data in the clear.
CLEARTEXT = {
    21:  ("ftp",    "FTP transmits credentials and data in cleartext"),
    23:  ("telnet", "Telnet transmits credentials and all session data in cleartext"),
    25:  ("smtp",   "SMTP without enforced STARTTLS can expose mail in transit"),
    110: ("pop3",   "POP3 without TLS exposes mailbox credentials"),
    143: ("imap",   "IMAP without TLS exposes mailbox credentials"),
    513: ("rlogin", "rlogin is an unauthenticated legacy remote-access protocol"),
    514: ("shell",  "rsh trusts the client's word for identity"),
}

# Datastores that should essentially never face the public internet.
EXPOSED_DATASTORES = {
    1433:  "Microsoft SQL Server",
    3306:  "MySQL / MariaDB",
    5432:  "PostgreSQL",
    6379:  "Redis (historically unauthenticated by default)",
    9200:  "Elasticsearch (historically unauthenticated by default)",
    11211: "Memcached (amplification vector when UDP-reachable)",
    27017: "MongoDB (historically unauthenticated by default)",
}

# Remote-administration surfaces worth calling out when reachable.
REMOTE_ADMIN = {
    445:  ("SMB", "high"),
    3389: ("RDP", "high"),
    5900: ("VNC", "high"),
    5985: ("WinRM", "medium"),
    2375: ("Docker daemon (unauthenticated TCP)", "critical"),
    2379: ("etcd client API", "high"),
    10250: ("kubelet API", "high"),
}

# Product/version pairs old enough to be worth flagging for verification.
# Kept deliberately small and conservative — the point is to demonstrate
# version-aware triage, not to ship a vulnerability database.
EOL_HINTS = [
    (r"OpenSSH\s+([0-6]\.|7\.[0-3])", "high",
     "OpenSSH build predates 7.4; several user-enumeration and key-handling issues apply"),
    (r"Apache httpd\s+2\.2", "high",
     "Apache httpd 2.2 reached end of life in 2018 and receives no security fixes"),
    (r"Apache httpd\s+2\.4\.(?:[0-9]|[1-2][0-9]|3[0-9])(?!\d)", "medium",
     "Apache httpd 2.4.x below 2.4.40 misses a long run of security fixes"),
    (r"nginx\s+1\.(?:[0-9]|1[0-2])\.", "medium",
     "nginx below 1.14 is out of support"),
    (r"vsftpd\s+2\.3\.4", "critical",
     "vsftpd 2.3.4 is the backdoored release (CVE-2011-2523)"),
    (r"ProFTPD\s+1\.3\.[0-3]", "high",
     "ProFTPD 1.3.0-1.3.3 covers several remote-code-execution advisories"),
    (r"Microsoft-IIS/[0-6]\.", "high",
     "IIS 6 and below are long out of support"),
    (r"PHP/[45]\.", "high",
     "PHP 4/5 are end of life and unsupported"),
]

WEB_PORTS = {80, 8080, 8000, 8888}


def _finding(severity: str, title: str, evidence: str, rationale: str,
             host: str, port: int | None = None) -> dict:
    return {
        "severity": severity,
        "title": title,
        "evidence": evidence,
        "rationale": rationale,
        "host": host,
        "port": port,
    }


def _version_string(p: dict) -> str:
    return " ".join(x for x in (p.get("product", ""), p.get("version", "")) if x).strip()


def analyse_host(host: dict) -> list[dict]:
    """Applies every rule to one host and returns its findings."""
    findings: list[dict] = []
    label = host["label"]
    ports = host["open_ports"]
    open_numbers = {p["port"] for p in ports}

    for p in ports:
        num, name = p["port"], p["name"]
        version = _version_string(p)
        where = f"{num}/{p['protocol']} ({name}{' ' + version if version else ''})"

        if num in CLEARTEXT:
            _, why = CLEARTEXT[num]
            sev = "critical" if num in (23, 513, 514) else "high"
            findings.append(_finding(
                sev, f"Cleartext service exposed on port {num}", where, why, label, num))

        if num in EXPOSED_DATASTORES:
            findings.append(_finding(
                "critical", f"Database service reachable on port {num}", where,
                f"{EXPOSED_DATASTORES[num]} is listening on a network-reachable port; "
                "datastores should sit behind a private network or firewall.",
                label, num))

        if num in REMOTE_ADMIN:
            svc, sev = REMOTE_ADMIN[num]
            findings.append(_finding(
                sev, f"Remote administration surface: {svc}", where,
                f"{svc} grants broad control of the host and is a primary target for "
                "credential-stuffing and known-exploit attacks.", label, num))

        for pattern, sev, why in EOL_HINTS:
            if version and re.search(pattern, version, re.IGNORECASE):
                findings.append(_finding(
                    sev, f"Outdated software: {version}", where, why, label, num))
                break

        if name in ("unknown", "") and num > 1024:
            findings.append(_finding(
                "low", f"Unidentified service on high port {num}", where,
                "nmap could not fingerprint this service. Unrecognised listeners on "
                "high ports are worth confirming as intentional.", label, num))

    # Host-level observations, which need the whole port list to judge.
    if 80 in open_numbers and 443 not in open_numbers:
        findings.append(_finding(
            "medium", "HTTP served without HTTPS", "80/tcp open, 443/tcp closed",
            "Traffic to this host has no TLS option, so sessions and credentials "
            "travel in the clear.", label, 80))

    if len(ports) >= 15:
        findings.append(_finding(
            "medium", f"Large attack surface: {len(ports)} open ports",
            ", ".join(str(p["port"]) for p in ports[:15]) + "…",
            "A host exposing this many services is unlikely to be applying least "
            "privilege; each listener is an independent entry point.", label))

    if not ports:
        findings.append(_finding(
            "info", "No open ports found", "host responded but exposed no TCP ports",
            "Either well firewalled, or the scan profile was too narrow to reach "
            "its listening ports.", label))

    return findings


def analyse(scan: dict) -> list[dict]:
    """Runs the rules over every host, worst findings first."""
    findings = [f for host in scan["hosts"] for f in analyse_host(host)]
    findings.sort(key=lambda f: (SEVERITY_ORDER.index(f["severity"]), f["host"],
                                 f["port"] or 0))
    return findings


def severity_counts(findings: list[dict]) -> dict[str, int]:
    counts = {s: 0 for s in SEVERITY_ORDER}
    for f in findings:
        counts[f["severity"]] += 1
    return counts


def format_findings(findings: list[dict]) -> str:
    """Renders findings as the evidence block handed to the LLM analyst."""
    if not findings:
        return "No rule-based findings."
    lines = []
    for i, f in enumerate(findings, start=1):
        target = f["host"] + (f":{f['port']}" if f["port"] else "")
        lines.append(
            f"{i}. [{f['severity'].upper()}] {f['title']} — {target}\n"
            f"   evidence : {f['evidence']}\n"
            f"   rationale: {f['rationale']}"
        )
    return "\n".join(lines)
