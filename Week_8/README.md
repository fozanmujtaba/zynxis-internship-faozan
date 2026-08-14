# Week 8 — Capstone: Agentic Code Auditor

**Task:** Deploy a production-ready agentic workflow. Deliverables: full repo
+ 1-page project case study.

A code auditor that walks a Python repository, proves what it can with static
analysis, asks a language model only about what it cannot, and labels every
finding with how much it should be trusted.

**→ [case_study.md](case_study.md) · [case_study.pdf](case_study.pdf)**

## Pipeline

```
  discover ─► static analysis ─► secret scan ─► LLM review ─► summary ─► report
   (code)         (AST)          (patterns +     (targeted)    (LLM)
                                   entropy)
      │              │                │              │
   prune venv/    13 rules over    provider keys   only files
   node_modules   the syntax       + Shannon       already flagged
   /binaries      tree             entropy         by the stages above
```

Deterministic stages run first and always. The LLM stage is optional, narrow,
and non-fatal: if the model is unreachable the audit still produces a complete
static report.

## What This Demonstrates

| Concept | How it's shown |
|---|---|
| Grounded analysis | `static.py` walks the AST, so `"never call eval(x)"` in a string doesn't fire — provable findings, not pattern guesses |
| Trust calibration | Every finding is `confirmed`, `probable`, or `advisory`, and the report explains the difference |
| Selective LLM use | `select_for_review()` sends only already-suspicious files to the model, ranked by severity of existing findings |
| Resilience | Retry with jittered backoff, `Retry-After` support, and a circuit breaker for hard quota exhaustion |
| Cost control | Content-addressed disk cache + per-run token accounting |
| Graceful degradation | `--no-llm`, or any API failure, yields a complete deterministic report |
| Auditability | Suppressed findings are counted and listed, never silently dropped |
| Correctness | 18 tests, each rule with positive **and** negative cases |

## Why static analysis comes first

Ask a model "is this code safe?" twice and you get two different answers. That
is fine for a suggestion and fatal for a report someone must act on.

So the checkable judgements happen in Python, where they are deterministic and
regression-testable: thirteen AST rule classes and a secret scanner. The model
is then asked for what rules genuinely cannot express — logic errors, missing
validation, unsafe assumptions — over a small set of already-suspicious files.

The confidence label carries that split into the output. `confirmed` findings
are proven by the syntax tree. `advisory` findings are a model's opinion about
code it could not run. Presenting those as equals is what makes AI code review
untrustworthy; separating them is what makes it useful.

## Setup

```bash
cd Week_8
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

The `.env` file holds `GROQ_API_KEY` (same key as Weeks 1-7).

## Run

```bash
# Audit this whole repository (default)
python audit.py

# Deterministic stages only — zero API calls
python audit.py --no-llm

# A single week, with a wider LLM review
python audit.py --path ../Week_6 --max-review 8

# Ignore the cache and re-query the model
python audit.py --no-cache

# Tests
python -m pytest tests/ -q

# Render the deliverables
python generate_report.py audit_report.md audit_report.pdf
python generate_report.py case_study.md case_study.pdf --compact
```

## Results

Audited against this repository — 37 files, ~4,600 lines, all eight weeks:

| Metric | Cold run | Warm run |
|---|---|---|
| Findings | 34 (3 critical · 5 high · 8 medium · 18 low) | 34 |
| LLM calls | 7 | **0** |
| Tokens | 18,315 | **0** |
| Retries | 0 | 0 |

Tests: **18/18 passing**.

**The auditor found a real issue in the author's own Week 1 code** — `eval()`
inside the ReAct agent's calculator tool ([Week_1/react_agent.py:29](../Week_1/react_agent.py#L29)).
It is sandboxed, but sandboxed `eval` is a documented escape target and is
exactly what a self-review misses.

**It also got things wrong first, which is recorded rather than hidden.** The
initial run produced 12 findings, 7 of them false positives: an enum member
named `SECRET = "secret-scan"` read as a hardcoded credential, and the tool's
own test fixtures — including AWS's published example key — read as leaked
secrets. Both classes were fixed by adding discrimination (a lowercase-slug
and entropy filter; a test-path policy) rather than by removing rules. The
full story is in [case_study.md](case_study.md).

| Deliverable | File |
|---|---|
| Case study | [case_study.pdf](case_study.pdf) · [.md](case_study.md) |
| Audit report | [audit_report.pdf](audit_report.pdf) · [.md](audit_report.md) |
| Structured findings | [audit_findings.json](audit_findings.json) |

## Rules implemented

| Rule | Severity | Catches |
|---|---|---|
| `PY-EVAL` | critical | `eval()` / `exec()` |
| `PY-HARDCODED-SECRET` | critical | credential assigned a high-entropy literal |
| `PY-OS-SYSTEM` | high | `os.system()` |
| `PY-SHELL-TRUE` | high | `subprocess(..., shell=True)` |
| `PY-PICKLE` | high | `pickle.load`/`loads` |
| `PY-YAML-LOAD` | high | `yaml.load()` without a safe Loader |
| `PY-WEAK-HASH` | medium | `hashlib.md5` / `sha1` |
| `PY-MKTEMP` | medium | race-prone `tempfile.mktemp()` |
| `PY-NO-TIMEOUT` | medium | `requests` call with no timeout |
| `PY-MUTABLE-DEFAULT` | medium | mutable default argument |
| `PY-SILENT-EXCEPT` | medium | bare `except:` that only `pass`es |
| `PY-BARE-EXCEPT` / `PY-SWALLOWED-EXCEPT` | low | bare or discarded exception handling |
| `PY-ASSERT` | low | `assert` for runtime validation (skipped in tests) |
| `SEC-*` | critical–high | AWS, GitHub, Slack, Stripe, Google, OpenAI, Groq keys, private key blocks, JWTs, DB URLs with passwords |

## Honest limitations

- **Python only.** The AST analyser cannot read the JavaScript or Go a real
  polyglot repo would contain.
- **Whole-repo, not diff.** Auditing a pull request's changed lines is what
  would make this usable in CI; it audits everything, every time.
- **The rule set is small.** Thirteen classes is a demonstration, not a
  replacement for Bandit or Semgrep, and there is no CWE mapping.
- **LLM findings are unverified.** They are labelled `advisory` precisely
  because nothing executes the code to confirm them. Some will be wrong.
- **Secrets are matched, not validated.** No key is tested against its
  provider, so a revoked key still reports as critical.

## Files

```
Week_8/
├── audit.py                  # CLI: discover -> analyse -> scan -> review -> report
├── auditor/
│   ├── models.py             # Finding, Severity, Source, AuditResult
│   ├── discover.py           # repo walking and file selection
│   ├── static.py             # AST rules
│   ├── secrets.py            # provider patterns + entropy detection
│   ├── llm.py                # resilient Groq client: retry, cache, accounting
│   ├── review.py             # LLM review + executive summary stages
│   └── report.py             # markdown rendering
├── tests/                    # 18 tests
├── case_study.md/.pdf        # deliverable: 1-page case study
├── audit_report.md/.pdf      # deliverable: example audit output
├── audit_findings.json       # structured findings
├── generate_report.py        # markdown -> PDF
├── .env                      # GROQ_API_KEY
├── requirements.txt
└── README.md
```
