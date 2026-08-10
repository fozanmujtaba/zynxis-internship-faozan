# Week 6 — Analysis Screenshots

Deliverable evidence for the Security Analyst agent. Save PNGs here using the
filenames below, so the sequence reads in order.

| File | What to capture | Command |
|---|---|---|
| `01-live-scan.png` | The live authorised nmap scan of `scanme.nmap.org` — the `$ nmap …` line, the parsed ports, and the 3 findings | `python security_agent.py` |
| `02-rules-triage.png` | The severity triage of the synthetic fixture — all 15 findings, colour-coded critical/high/medium | `python security_agent.py --xml sample_vulnerable_scan.xml --no-llm` |
| `03-llm-assessment.png` | The same run with the LLM analyst enabled, showing step `[4/4]` and the completion summary | `python security_agent.py --xml sample_vulnerable_scan.xml` |
| `04-report-pdf.png` | `security_report.pdf` open in a PDF viewer, showing the severity table | open the file in Preview |

All scanning shown is authorised: `scanme.nmap.org` is published by the Nmap
project for scan testing, and `sample_vulnerable_scan.xml` is synthetic data
that was never scanned from a real host.
