"""
Week 5 — Multi-Agent Orchestration
A CrewAI Researcher + Writer team that autonomously produces a ~10-page
market analysis report.

Structure of a run:

  Phase 1 (once)      Researcher  -> a market research brief for the topic
  Phase 2 (x10)       Researcher  -> focused findings for one report section
                      Writer      -> the prose for that section, from those findings

Each section is its own small Crew so that one bad section can't take down
the whole run, and so the handoff log stays readable per section.

Run modes:
  python crew.py                          → full 10-section report
  python crew.py --sections 2             → short run (useful for testing)
  python crew.py --topic "..."            → analyse a different market
"""

import argparse
import os
import sys
import time

from crewai import Agent, Crew, Task, Process, LLM
from dotenv import load_dotenv

from run_log import RunLog, capture_stdout, make_recorder, timed

load_dotenv()

# Groq is reached through its OpenAI-compatible endpoint rather than through
# LiteLLM's "groq/..." route. CrewAI 1.x only strips its internal
# `cache_breakpoint` marker inside the native-provider path (BaseLLM.
# _format_messages); the LiteLLM fallback forwards the marker verbatim and
# Groq rejects the request. Pointing the native OpenAI provider at Groq keeps
# us on the supported path and drops the LiteLLM dependency altogether.
MODEL     = "openai/llama-3.3-70b-versatile"
MODEL_ID  = "llama-3.3-70b-versatile"
GROQ_BASE = "https://api.groq.com/openai/v1"

DEFAULT_TOPIC = "the global Agentic AI platforms market (autonomous LLM agents for enterprise)"

REPORT_MD = "market_analysis.md"
BRIEF_MD  = "research_brief.md"
LOG_MD    = "interaction_log.md"
LOG_JSON  = "interaction_log.json"
LOG_RAW   = "crew_verbose.log"

BOLD  = "\033[1m"
CYAN  = "\033[96m"
GREEN = "\033[92m"
RESET = "\033[0m"

# The ten sections of the report. Each becomes one Researcher -> Writer pair,
# so the section list is also the orchestration plan.
SECTIONS = [
    ("Executive Summary",
     "the headline findings: what this market is, how big it is, how fast it is "
     "growing, who leads it, and the two or three things a decision-maker must know"),
    ("Market Definition and Scope",
     "what is and is not counted inside this market, the main product categories, "
     "and how the segment boundaries are drawn"),
    ("Market Size and Growth Forecast",
     "current market size, historical growth, forward CAGR, and the assumptions "
     "behind the forecast, with figures broken out by segment where possible"),
    ("Competitive Landscape",
     "the major vendors and challengers, their positioning and differentiation, "
     "and how market share is distributed"),
    ("Customer Segments and Demand Drivers",
     "who buys, what problem they are buying to solve, budget ownership, and the "
     "forces pushing adoption up or down"),
    ("Technology and Innovation Trends",
     "the technical shifts reshaping the market over the next 24 months and what "
     "they mean commercially"),
    ("Regulatory and Risk Factors",
     "the compliance regimes in play, legal exposure, and the operational and "
     "reputational risks buyers and vendors carry"),
    ("Regional Analysis",
     "how demand, maturity and regulation differ across North America, Europe, "
     "Asia-Pacific and the rest of the world"),
    ("Strategic Opportunities and Recommendations",
     "the concrete openings a new or scaling entrant should pursue, with the "
     "reasoning and trade-offs behind each"),
    ("Conclusion and Outlook",
     "a synthesis of the analysis and a clear-eyed three-year outlook, including "
     "what would have to be true for the optimistic case to hold"),
]


def build_llm() -> LLM:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        sys.exit("GROQ_API_KEY is not set — add it to Week_5/.env")
    return LLM(model=MODEL, api_key=api_key, base_url=GROQ_BASE, temperature=0.4)


def build_agents(llm: LLM) -> tuple[Agent, Agent]:
    researcher = Agent(
        role="Senior Market Research Analyst",
        goal=(
            "Assemble accurate, specific, decision-grade findings about {topic}. "
            "Prefer concrete figures, named companies and dated events over vague "
            "generalities."
        ),
        backstory=(
            "You have spent fifteen years writing industry research for institutional "
            "clients. You are known for refusing to pad a brief: if a number is an "
            "estimate you label it as one, and if the evidence is thin you say so "
            "rather than inventing precision that isn't there."
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )

    writer = Agent(
        role="Market Analysis Report Writer",
        goal=(
            "Turn the analyst's raw findings into the polished prose of a "
            "professional market analysis report on {topic}."
        ),
        backstory=(
            "You write the reports that partners actually read. You work strictly "
            "from the analyst's findings, never inventing facts of your own, and you "
            "write in flowing analytical paragraphs rather than shallow bullet lists."
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )

    return researcher, writer


def run_crew(agents: list[Agent], tasks: list[Task], log: RunLog, inputs: dict) -> str:
    """Kicks off a crew, mirroring its verbose chatter into the run log."""
    crew = Crew(agents=agents, tasks=tasks, process=Process.sequential, verbose=True)
    with capture_stdout() as buffer:
        result = crew.kickoff(inputs=inputs)
    log.add_verbose(buffer.getvalue())
    return str(result)


def phase_brief(researcher: Agent, topic: str, log: RunLog) -> str:
    """Phase 1 — one broad research brief that every section is written against."""
    print(f"\n{BOLD}[Phase 1] Researcher — building the market research brief{RESET}")

    task = Task(
        description=(
            "Produce a dense research brief on {topic}.\n\n"
            "Cover: how the market is defined, its approximate current size and "
            "growth rate, the leading vendors and their positioning, the main "
            "customer segments, the technical and regulatory forces acting on it, "
            "and the biggest open questions.\n\n"
            "Be specific. Name companies. Give figures where you can, and mark "
            "them as estimates when they are estimates. This brief is the single "
            "source of truth every later section is written from, so do not leave "
            "gaps you expect someone else to fill."
        ),
        expected_output=(
            "A structured research brief of 600-900 words, organised under clear "
            "headings, containing concrete named entities and figures."
        ),
        agent=researcher,
        callback=make_recorder(log, "brief", researcher.role,
                               "Market research brief", [time.time()]),
    )

    with timed() as elapsed:
        brief = run_crew([researcher], [task], log, {"topic": topic})

    print(f"{GREEN}  brief ready — {len(brief)} chars in {elapsed[0]:.1f}s{RESET}")
    return brief


def phase_section(
    researcher: Agent, writer: Agent, topic: str, brief: str,
    title: str, focus: str, index: int, total: int, log: RunLog,
) -> str:
    """Phase 2 — Researcher finds, Writer writes, for a single report section."""
    print(f"\n{BOLD}[Section {index}/{total}] {title}{RESET}")

    # Both callbacks share one clock, so each turn is measured from the moment
    # the previous agent handed off rather than from the start of the section.
    clock = [time.time()]

    research_task = Task(
        description=(
            f"The report section you are supporting is '{title}'.\n"
            f"It must cover {focus}.\n\n"
            "Using the market brief below as your foundation, work out the "
            "findings this specific section needs. Go deeper than the brief "
            "does — pull out the particular figures, companies, examples and "
            "causal arguments that belong in this section and nowhere else.\n\n"
            "Do not write prose. Produce findings the writer can build from.\n\n"
            # The brief is passed as a CrewAI input rather than f-string'd in.
            # Task descriptions go through interpolate_only(), which raises
            # KeyError on any {placeholder} it can't resolve — and the brief is
            # LLM-written text that may legitimately contain braces. Substituted
            # *values* are not re-scanned, so this route is brace-safe.
            "--- MARKET BRIEF ---\n{brief}\n--- END BRIEF ---"
        ),
        expected_output=(
            "A tight set of findings for this section: specific facts, figures, "
            "named examples and the analytical points they support."
        ),
        agent=researcher,
        callback=make_recorder(log, "section", researcher.role,
                               f"Findings — {title}", clock),
    )

    write_task = Task(
        description=(
            f"Write the '{title}' section of a professional market analysis "
            f"report on {{topic}}.\n\n"
            f"The section must cover {focus}.\n\n"
            "Work only from the analyst's findings in your context. Write 500-700 "
            "words of flowing analytical prose — full paragraphs that make an "
            "argument, not a list of bullets. You may use a short table or a few "
            "bullets where they genuinely carry the information better.\n\n"
            f"Start with the markdown heading '## {title}' and write nothing "
            "before it. Do not add a concluding meta-sentence about the section "
            "itself."
        ),
        expected_output=(
            f"The finished '{title}' section in markdown, opening with the "
            f"'## {title}' heading."
        ),
        agent=writer,
        context=[research_task],
        callback=make_recorder(log, "section", writer.role, f"Draft — {title}", clock),
    )

    with timed() as elapsed:
        section = run_crew(
            [researcher, writer], [research_task, write_task], log,
            {"topic": topic, "brief": brief},
        )

    print(f"{GREEN}  section ready — {len(section)} chars in {elapsed[0]:.1f}s{RESET}")
    return section


def split_report(path: str) -> dict[str, str]:
    """Reads an existing report back into a {section title: markdown} map.

    Used by --only, so a single failed section can be regenerated without
    paying to rebuild the nine that already came out fine.
    """
    titles = {title for title, _ in SECTIONS}
    blocks: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []

    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("## ") and line[3:].strip() in titles:
                if current:
                    blocks[current] = "".join(buf).rstrip()
                current = line[3:].strip()
                buf = [line]
            elif current:
                buf.append(line)

    if current:
        blocks[current] = "".join(buf).rstrip()
    return blocks


def assemble(topic: str, sections: list[str], log: RunLog) -> str:
    header = [
        "# Market Analysis Report",
        "",
        f"## {topic.strip().rstrip('.')}",
        "",
        "**Prepared by:** an autonomous CrewAI Researcher + Writer team  ",
        "**Author (orchestration):** Faozan Mujtaba — Zynxis Agentic AI Internship, Week 5  ",
        f"**Generated:** {log.started_at.strftime('%d %B %Y')}  ",
        f"**Model:** {MODEL_ID} (Groq)",
        "",
        "> This report was written end to end by two collaborating LLM agents. No "
        "section was drafted or edited by a human. Figures are the model's own "
        "estimates and are presented as an exercise in agent orchestration, not as "
        "verified market data.",
        "",
        "---",
        "",
    ]
    return "\n".join(header) + "\n\n".join(s.strip() for s in sections) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Researcher + Writer crew.")
    parser.add_argument("--topic", default=DEFAULT_TOPIC, help="market to analyse")
    parser.add_argument("--sections", type=int, default=len(SECTIONS),
                        help="how many sections to generate (default: all 10)")
    parser.add_argument("--only", metavar="N[,N...]",
                        help="regenerate just these section numbers (1-10) and splice "
                             "them into the existing report — for recovering from a "
                             "section that failed mid-run")
    args = parser.parse_args()

    repair = bool(args.only)
    if repair:
        wanted = sorted({int(n) for n in args.only.split(",") if n.strip()})
        sections_to_run = [SECTIONS[n - 1] for n in wanted if 1 <= n <= len(SECTIONS)]
        if not sections_to_run:
            sys.exit(f"--only expects section numbers between 1 and {len(SECTIONS)}")
        if not os.path.exists(REPORT_MD):
            sys.exit(f"--only needs an existing {REPORT_MD} to splice into")
    else:
        sections_to_run = SECTIONS[: max(1, min(args.sections, len(SECTIONS)))]

    # A repair run must not clobber the interaction log of the full run it is
    # patching, so it writes its own set alongside it.
    log_md, log_json, log_raw = (
        ("interaction_log_repair.md", "interaction_log_repair.json", "crew_verbose_repair.log")
        if repair else (LOG_MD, LOG_JSON, LOG_RAW)
    )

    print(f"\n{BOLD}Multi-Agent Market Analysis — Week 5{RESET}")
    print("=" * 70)
    print(f"Topic    : {args.topic}")
    print(f"Model    : {MODEL_ID} (Groq)")
    print(f"Agents   : Senior Market Research Analyst + Market Analysis Report Writer")
    print(f"Sections : {len(sections_to_run)}"
          + (f" (repairing {', '.join(t for t, _ in sections_to_run)})" if repair else ""))
    print("=" * 70)

    log = RunLog(args.topic)
    llm = build_llm()
    researcher, writer = build_agents(llm)

    # Reuse the cached brief on a repair run: rebuilding it costs tokens and
    # would give the patched section a different foundation to the other nine.
    if repair and os.path.exists(BRIEF_MD):
        with open(BRIEF_MD, encoding="utf-8") as f:
            brief = f.read()
        print(f"\n{CYAN}Reusing cached research brief{RESET} ({len(brief)} chars)")
    else:
        brief = phase_brief(researcher, args.topic, log)
        with open(BRIEF_MD, "w", encoding="utf-8") as f:
            f.write(brief)

    written: dict[str, str] = split_report(REPORT_MD) if repair else {}

    for i, (title, focus) in enumerate(sections_to_run, start=1):
        try:
            written[title] = phase_section(researcher, writer, args.topic, brief,
                                           title, focus, i, len(sections_to_run), log)
        except Exception as exc:  # one bad section shouldn't lose the whole run
            print(f"\033[91m  section failed: {exc}{RESET}")
            written.setdefault(title, f"## {title}\n\n*This section failed to generate: {exc}*")

    ordered = [title for title, _ in (SECTIONS if repair else sections_to_run)]
    report = assemble(args.topic, [written[t] for t in ordered if t in written], log)

    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write(report)
    log.write_markdown(log_md)
    log.write_json(log_json)
    log.write_verbose(log_raw)

    words = len(report.split())
    print(f"\n{BOLD}{'=' * 70}{RESET}")
    print(f"{GREEN}Done.{RESET} {len(log.events)} agent turns in {log.elapsed():.0f}s")
    print(f"  {REPORT_MD:<28} {words} words (~{words / 500:.1f} pages)")
    print(f"  {log_md:<28} readable handoff log")
    print(f"  {log_json:<28} structured log")
    print(f"  {log_raw:<28} raw crew stdout")
    print(f"\n{CYAN}Next:{RESET} python generate_report.py {REPORT_MD} market_analysis.pdf")


if __name__ == "__main__":
    main()
