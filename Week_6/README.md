# Week 6 — Agentic Cybersecurity

**Task:** Create a Security Analyst agent that uses Nmap results to flag
suspicious activity and suggest vulnerabilities.

> **Scope and authorisation.** Everything here targets either
> `scanme.nmap.org` — the host the Nmap project publishes expressly for scan
> testing — or a synthetic XML fixture that was never scanned at all. The
> agent refuses by default to scan anything outside a small allow-list, and
> requires an explicit `--authorised` flag to touch any other host. Scanning
> machines you neither own nor have permission to test is illegal in most
> jurisdictions.

## What This Demonstrates

| Concept | How it's shown |
|---|---|
| Tool-driven agent | `scan.py` shells out to the real `nmap` binary and parses its XML into a flat structure the model never has to read |
| Grounded reasoning | `rules.py` makes the checkable judgements in plain Python *first*; the LLM receives confirmed findings as evidence rather than being asked to spot them |
| Severity triage | Every finding carries a severity, evidence, and a rationale, sorted worst-first before the model ever sees it |
| Analyst judgement | `analyst.py` asks the model to do what rules can't — weigh findings against each other, connect them, and order the fixes |
| Hallucination control | The prompt forbids invented CVE identifiers and forces a CONFIRMED / REQUIRES VERIFICATION label on every claimed vulnerability |
| Graceful degradation | If the API is unavailable or rate-limited, the run falls back to a complete rules-only report instead of failing |
| Safety guardrail | `check_authorised()` blocks scans of third-party hosts unless authorisation is explicitly asserted |

## Pipeline

```
   nmap ──► parse XML ──► rules engine ──► LLM analyst ──► report
  (tool)    (scan.py)      (rules.py)      (analyst.py)   (.md/.pdf)
                               │                │
                        deterministic      judgement,
                        severity + evidence  priority, remediation
```

## Why a rules engine sits in front of the model

An LLM asked "is this port list dangerous?" is inconsistent — it will call
port 23 critical in one run and shrug at it in the next. So the boring,
checkable decisions happen in Python, where they are deterministic and
reviewable: cleartext protocols, exposed datastores, remote-administration
surfaces, end-of-life software versions, and host-level observations like
"HTTP with no HTTPS" or "22 open ports."

The model is then handed those confirmed findings and asked to do the part it
is genuinely good at: judging what matters most on *this* host, spotting
combinations, and writing remediation someone can act on. That split is what
makes the output reproducible enough to be worth reading.

## Setup

```bash
brew install nmap                # the agent shells out to the real binary

cd Week_6
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

The `.env` file holds `GROQ_API_KEY` (same key as Weeks 1-5).

## Run

```bash
# Live scan of the Nmap project's designated test host
python security_agent.py

# Rules engine only — zero API calls, useful when rate-limited
python security_agent.py --xml sample_scan.xml --no-llm

# The synthetic vulnerable fixture (exercises every rule)
python security_agent.py --xml sample_vulnerable_scan.xml

# Wider scan, or a host you are authorised to test
python security_agent.py --profile standard
python security_agent.py --target 192.168.1.10 --authorised

# Render the assessment
python generate_report.py security_report.md security_report.pdf
```

## Results

Two assessments are included.

**1. Live scan — `scanme.nmap.org`** ([security_report_scanme.pdf](security_report_scanme.pdf))

A real `nmap -sT -sV -F` scan. Two open ports, three findings:

```
HIGH     Outdated software: OpenSSH 6.6.1p1    scanme.nmap.org:22
MEDIUM   Outdated software: Apache httpd 2.4.7 scanme.nmap.org:80
MEDIUM   HTTP served without HTTPS             scanme.nmap.org:80
```

**2. Synthetic fixture — `sample_vulnerable_scan.xml`** ([security_report.pdf](security_report.pdf))

A well-maintained host exercises almost none of the rules, so
`make_sample.py` fabricates a scan modelled on the port layout of
Metasploitable 2, a deliberately vulnerable training VM. **Nothing was
scanned to produce this file.** It yields 22 open ports and 15 findings —
6 critical, 7 high, 2 medium — covering every rule category:

```
CRITICAL  Outdated software: vsftpd 2.3.4          :21   (backdoored release)
CRITICAL  Cleartext service exposed on port 23     :23   (telnet)
CRITICAL  Cleartext service exposed on port 513    :513  (rlogin)
CRITICAL  Cleartext service exposed on port 514    :514  (rsh)
CRITICAL  Database service reachable on port 3306  :3306 (MySQL)
CRITICAL  Database service reachable on port 5432  :5432 (PostgreSQL)
HIGH      ... 7 more
MEDIUM    Large attack surface: 22 open ports
MEDIUM    HTTP served without HTTPS                :80
```

`console_session.txt` is a captured terminal transcript of that run, colour
codes included — run `cat console_session.txt` in a terminal to replay it for
screenshots.

## Honest limitations

- **The end-of-life table is a demonstration, not a vulnerability database.**
  `EOL_HINTS` holds a dozen conservative patterns. A real deployment would
  query the NVD or an OSV feed rather than regex a banner.
- **Version banners can lie.** Distributions routinely backport security
  fixes without changing the advertised version, so a "HIGH — outdated
  OpenSSH" finding on a patched Ubuntu box may be a false positive. This is
  why version findings are labelled REQUIRES VERIFICATION rather than
  CONFIRMED.
- **`-sT -sV` only.** OS fingerprinting (`-O`) and SYN scanning (`-sS`)
  need root, and a deliverable that demands `sudo` is one nobody runs. The
  agent therefore never sees OS-level evidence.
- **The agent doesn't act.** It reports; it does not reconfigure firewalls or
  patch anything. Given that the findings are inferences, that boundary is
  deliberate.

## Files

```
Week_6/
├── security_agent.py             # CLI: scan -> triage -> analyse -> report
├── scan.py                       # nmap wrapper, XML parser, authorisation guard
├── rules.py                      # deterministic triage rules and severities
├── analyst.py                    # LLM analyst prompt and call
├── make_sample.py                # builds the synthetic vulnerable fixture
├── generate_report.py            # markdown -> PDF
├── scan.xml                      # raw nmap XML from the live scan
├── sample_scan.xml               # saved live scan (reproducible offline)
├── sample_vulnerable_scan.xml    # synthetic fixture — never scanned
├── security_report.md/.pdf       # deliverable: assessment of the fixture
├── security_report_scanme.md/.pdf# deliverable: assessment of the live scan
├── findings.json                 # structured scan + findings
├── console_session.txt           # terminal transcript for screenshots
├── .env                          # GROQ_API_KEY
├── requirements.txt
└── README.md
```
