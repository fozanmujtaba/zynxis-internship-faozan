# Week 5 — Multi-Agent Orchestration

**Task:** Use CrewAI to set up a Researcher + Writer team that autonomously
generates a 10-page market analysis report.

## What This Demonstrates

| Concept | How it's shown |
|---|---|
| Agent roles | Two agents with distinct roles, goals and backstories — a research analyst who gathers findings and a writer who is forbidden from inventing facts of its own |
| Task orchestration | 21 tasks across 11 crews, run as `Process.sequential`, driven by the `SECTIONS` list in `crew.py` |
| Inter-agent handoff | The writer never sees the raw topic alone — CrewAI's `context=[research_task]` pipes the analyst's findings straight into the writer's prompt |
| Shared grounding | One research brief is generated once and injected into every section, so ten independently written sections agree on the same figures |
| Interaction logging | Per-task callbacks record who acted, when, for how long, and what they produced — into both a readable and a machine-readable log |
| Failure isolation | Each section is its own crew, so one failed section can't take down the run, and `--only` can repair it afterwards |

## Architecture

```
                    ┌──────────────────────────┐
   topic ─────────► │ Researcher               │  Phase 1, once
                    │ Senior Market Research   │
                    │ Analyst                  │
                    └────────────┬─────────────┘
                                 │ research brief (~6k chars)
                                 ▼
                    ┌──────────────────────────┐
                    │ cached: research_brief.md│
                    └────────────┬─────────────┘
                                 │ injected into every section below
        ┌────────────────────────┴────────────────────────┐
        ▼                                                 ▼
  ┌───────────────┐  findings   ┌───────────────┐   ... x10 sections
  │ Researcher    │ ──────────► │ Writer        │
  │ (deep-dive on │  CrewAI     │ (drafts the   │
  │  one section) │  context=   │  section)     │
  └───────────────┘             └───────┬───────┘
                                        │ markdown section
                                        ▼
                            market_analysis.md  ──► market_analysis.pdf
                            interaction_log.md  ──► interaction_log.pdf
```

Phase 1 runs once. Phase 2 runs the Researcher → Writer pair once per section,
each pair as its own small `Crew`.

## Why the report is built section by section

A single "write a 10-page report" task does not produce ten pages — models
converge on roughly a page and stop. Driving the report from an explicit
10-section plan gives the length the deliverable asks for, and it turns the
report outline into the orchestration plan: each section is one
Researcher → Writer handoff, which is also what makes the interaction log
worth reading.

## Model connection

Groq is reached through its **OpenAI-compatible endpoint**
(`https://api.groq.com/openai/v1`) rather than LiteLLM's `groq/...` route.

CrewAI 1.x only strips its internal `cache_breakpoint` marker inside the
native-provider path (`BaseLLM._format_messages`). The LiteLLM fallback
forwards that marker verbatim, and Groq rejects the request with
`property 'cache_breakpoint' is unsupported`. Pointing the native OpenAI
provider at Groq stays on the supported path and drops the LiteLLM dependency
entirely.

## Setup

```bash
cd Week_5
python3.11 -m venv venv          # CrewAI 1.x does not support Python 3.14
source venv/bin/activate
pip install -r requirements.txt
```

The `.env` file holds `GROQ_API_KEY` (same key as Weeks 1-4).

## Run

```bash
# Full report — 21 agent turns, ~3 minutes
python crew.py

# Short run, useful when testing changes
python crew.py --sections 2

# A different market
python crew.py --topic "the global vector database market"

# Repair a section that failed mid-run, reusing the cached brief
python crew.py --only 10

# Render the deliverables
python generate_report.py market_analysis.md market_analysis.pdf
python generate_report.py interaction_log.md interaction_log.pdf
```

## Results

A full run is **21 agent turns in ~3 minutes** — one Phase 1 brief plus ten
Researcher → Writer handoffs — yielding an **11-page, 8,475-word market
analysis report** on the global Agentic AI platforms market.

The committed run logged **19 turns in 147s** before exhausting the day's Groq
token allowance on its final section. That section was regenerated the next
day with `--only 10` against the cached brief, in 2 turns and 6 seconds
instead of a second full run. The shipped report has all ten sections and no
failure placeholders; `interaction_log.*` covers the 19-turn main run and
`interaction_log_repair.*` covers the 2-turn repair.

| Deliverable | File |
|---|---|
| Final generated report | [market_analysis.pdf](market_analysis.pdf) · [.md](market_analysis.md) |
| Agent interaction log | [interaction_log.pdf](interaction_log.pdf) · [.md](interaction_log.md) |
| Structured log | [interaction_log.json](interaction_log.json) |
| Raw crew stdout | [crew_verbose.log](crew_verbose.log) |

## Rate limits — worth knowing before you run it

A full 21-turn run consumes close to **100,000 Groq tokens**, which is the
entire free-tier daily allowance. The first full run of this pipeline hit
that ceiling on its last section and returned HTTP 429.

That is what `--only` exists for: rather than spending another full day's
budget re-running nine sections that were already fine, `--only 10`
regenerates just the failed one against the cached brief and splices it back
into the report. The repair run's logs are written to
`interaction_log_repair.*` so they don't overwrite the log of the full run
they're patching.

## Honest limitations

- **The agents have no search tool.** Every figure in the report comes from
  the model's own parametric knowledge, so the numbers should be read as
  plausible-looking synthetic estimates, not verified market data. The report
  says so on its first page. Adding a real search tool is the obvious next
  step, and is exactly what Week 2's tool-calling work would plug into here.
- **Sequential process only.** `Process.hierarchical` with a manager agent
  would be a stronger demonstration of delegation, but it multiplies token
  cost — which the free-tier ceiling above rules out for a 10-section report.
- **Sections can drift.** The shared brief keeps the headline figures
  consistent, but the ten sections are written independently and do repeat
  themselves across section boundaries. A dedicated editor agent doing a
  final consistency pass would fix this.

## Files

```
Week_5/
├── crew.py                     # agents, tasks, orchestration, CLI
├── run_log.py                  # stdout capture + structured interaction logging
├── generate_report.py          # markdown -> PDF (adds tables/quotes over Week 4's)
├── market_analysis.md/.pdf     # deliverable: the generated report
├── interaction_log.md/.pdf     # deliverable: readable agent handoff log
├── interaction_log.json        # structured log (per-turn timing + full output)
├── interaction_log_repair.*    # logs from the --only 10 repair run
├── crew_verbose.log            # raw CrewAI stdout
├── research_brief.md           # cached Phase 1 brief (reused by --only)
├── .env                        # GROQ_API_KEY
├── requirements.txt
└── README.md
```
