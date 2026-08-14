"""
Week 7 — The LLM stages of the Startup Operations Agent.

Three separate calls rather than one big one, because each asks for a
different kind of judgement and each output constrains the next:

  1. analyse      — read the raw brief, name what is actually being asked for,
                    and surface the ambiguities a delivery lead would chase
  2. break_down   — turn that into epics and tasks with estimates and
                    dependencies (the scheduler's input)
  3. tech_stack   — recommend a stack, justified against those requirements

Every stage returns JSON. Groq supports response_format json_object, which
removes the "model wrapped it in a code fence" class of failure entirely.
"""

from __future__ import annotations

import json
import os

from groq import Groq
from dotenv import load_dotenv

load_dotenv()

MODEL = "llama-3.3-70b-versatile"

VALID_ROLES = [
    "Product Manager", "UX Designer", "Frontend Engineer", "Backend Engineer",
    "Mobile Engineer", "Data Engineer", "ML Engineer", "DevOps Engineer",
    "QA Engineer", "Security Engineer",
]


class StageError(RuntimeError):
    pass


def build_client() -> Groq:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise StageError("GROQ_API_KEY is not set — add it to Week_7/.env")
    return Groq(api_key=key)


def _call_json(client: Groq, system: str, user: str, temperature: float = 0.3) -> dict:
    """One JSON-mode call, with the parse failure surfaced rather than swallowed."""
    response = client.chat.completions.create(
        model=MODEL,
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    raw = response.choices[0].message.content
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StageError(f"model returned invalid JSON: {exc}\n---\n{raw[:500]}") from exc


# ---------------------------------------------------------------- stage 1

ANALYSE_SYSTEM = """\
You are a delivery lead at a software consultancy, reading a new client brief
for the first time. Your job is to work out what is genuinely being asked for,
what has been left unsaid, and what would sink the project if assumed wrongly.

Clients write vague briefs. The valuable part of this job is naming the
ambiguities rather than quietly inventing answers to them.

Respond only with JSON.\
"""

ANALYSE_USER = """\
Read this client brief and analyse it.

--- BRIEF ---
{brief}
--- END BRIEF ---

Return JSON with exactly these keys:
{{
  "project_name": "short descriptive name",
  "summary": "2-3 sentences on what is being built and for whom",
  "objectives": ["the business outcomes this must achieve"],
  "in_scope": ["capabilities clearly requested"],
  "out_of_scope": ["things a reader might assume are included but are not"],
  "open_questions": [
    {{"question": "what you need the client to answer",
      "why_it_matters": "what changes depending on the answer",
      "assumption": "what you will assume until they answer"}}
  ],
  "risks": [
    {{"risk": "...", "severity": "high|medium|low", "mitigation": "..."}}
  ],
  "complexity": "low|medium|high"
}}

Give 3-6 open questions. They are the most valuable part of this analysis, so
make them specific to this brief — not generic project-management filler.\
"""


def analyse(client: Groq, brief: str) -> dict:
    return _call_json(client, ANALYSE_SYSTEM, ANALYSE_USER.format(brief=brief))


# ---------------------------------------------------------------- stage 2

BREAKDOWN_SYSTEM = """\
You are a technical delivery lead producing the work breakdown for a project
that has been scoped and is about to start.

Estimating rules:
- Estimates are in ideal working days for one person, and must be realistic
  for a competent engineer who still has meetings.
- No task may exceed 10 days. Split anything bigger — a 20-day task is an
  admission you have not thought about it.
- Dependencies must be real. Do not serialise work that could run in parallel;
  a plan where everything depends on everything is a plan with no schedule.

Respond only with JSON.\
"""

BREAKDOWN_USER = """\
Produce the work breakdown for this project.

PROJECT: {project_name}
SUMMARY: {summary}

IN SCOPE:
{in_scope}

OUT OF SCOPE (do not plan work for these):
{out_of_scope}

ASSUMPTIONS you are planning against:
{assumptions}

Return JSON with exactly these keys:
{{
  "epics": [
    {{"id": "E1", "name": "...", "goal": "what this epic delivers"}}
  ],
  "tasks": [
    {{"id": "T1",
      "epic": "E1",
      "title": "specific, verb-first, e.g. 'Build password reset flow'",
      "detail": "one sentence on what doing this actually involves",
      "role": "one of: {roles}",
      "estimate_days": 3,
      "depends_on": ["T-ids that must finish first, [] if none"]}}
  ]
}}

Produce 5-7 epics and 22-30 tasks covering the whole delivery: discovery and
design, build, integration, testing, security, deployment and launch. Task ids
must be unique and every id in depends_on must exist.\
"""


def break_down(client: Groq, analysis: dict) -> dict:
    assumptions = "\n".join(
        f"- {q.get('assumption', '')}" for q in analysis.get("open_questions", [])
    ) or "- none recorded"

    return _call_json(client, BREAKDOWN_SYSTEM, BREAKDOWN_USER.format(
        project_name=analysis.get("project_name", "Untitled"),
        summary=analysis.get("summary", ""),
        in_scope="\n".join(f"- {s}" for s in analysis.get("in_scope", [])) or "- unspecified",
        out_of_scope="\n".join(f"- {s}" for s in analysis.get("out_of_scope", [])) or "- none",
        assumptions=assumptions,
        roles=", ".join(VALID_ROLES),
    ))


# ---------------------------------------------------------------- stage 3

STACK_SYSTEM = """\
You are a principal engineer recommending a technology stack to a startup.

You are advising a small team who must ship and then live with this choice.
Favour boring, well-supported technology over novelty, and justify each choice
against this project's actual requirements rather than general popularity. Where
a credible alternative exists, name it and say why you did not pick it.

Respond only with JSON.\
"""

STACK_USER = """\
Recommend the stack for this project.

PROJECT: {project_name}
SUMMARY: {summary}
COMPLEXITY: {complexity}

REQUIREMENTS:
{in_scope}

KEY RISKS:
{risks}

Return JSON with exactly these keys:
{{
  "recommendations": [
    {{"layer": "e.g. Frontend, Backend, Database, Hosting, Auth, CI/CD, Monitoring",
      "choice": "the specific technology",
      "rationale": "why this fits THIS project's requirements",
      "alternative": "the credible runner-up",
      "why_not_alternative": "the specific reason it lost"}}
  ],
  "architecture_notes": ["how the pieces fit together, 3-5 points"],
  "scaling_considerations": ["what breaks first as usage grows, and the fix"]
}}

Cover 7-9 layers.\
"""


def tech_stack(client: Groq, analysis: dict) -> dict:
    risks = "\n".join(
        f"- [{r.get('severity', '?')}] {r.get('risk', '')}"
        for r in analysis.get("risks", [])
    ) or "- none recorded"

    return _call_json(client, STACK_SYSTEM, STACK_USER.format(
        project_name=analysis.get("project_name", "Untitled"),
        summary=analysis.get("summary", ""),
        complexity=analysis.get("complexity", "medium"),
        in_scope="\n".join(f"- {s}" for s in analysis.get("in_scope", [])) or "- unspecified",
        risks=risks,
    ))


# ---------------------------------------------------------------- validation

def validate_breakdown(breakdown: dict) -> list[str]:
    """Checks the model's task graph before the scheduler trusts it.

    Returns the repairs made. The agent reports these rather than hiding them:
    a plan silently patched is a plan you cannot audit.
    """
    repairs: list[str] = []
    tasks = breakdown.get("tasks", [])
    if not tasks:
        raise StageError("breakdown contained no tasks")

    seen: set[str] = set()
    for i, task in enumerate(tasks):
        tid = task.get("id") or f"T{i + 1}"
        if tid in seen:                       # duplicate ids would corrupt the graph
            new_id = f"{tid}-{i + 1}"
            repairs.append(f"duplicate task id {tid} renamed to {new_id}")
            tid = new_id
        task["id"] = tid
        seen.add(tid)

        try:
            estimate = float(task.get("estimate_days", 0))
        except (TypeError, ValueError):
            estimate = 0.0
        if estimate <= 0:
            repairs.append(f"{tid}: missing estimate, defaulted to 2 days")
            estimate = 2.0
        if estimate > 10:
            repairs.append(f"{tid}: estimate {estimate}d exceeds the 10-day cap, clamped")
            estimate = 10.0
        task["estimate_days"] = estimate

        if task.get("role") not in VALID_ROLES:
            repairs.append(f"{tid}: unrecognised role {task.get('role')!r}, "
                           "assigned Backend Engineer")
            task["role"] = "Backend Engineer"

    ids = {t["id"] for t in tasks}
    for task in tasks:
        deps = task.get("depends_on") or []
        if not isinstance(deps, list):
            deps = []
        kept = [d for d in deps if d in ids and d != task["id"]]
        if len(kept) != len(deps):
            dropped = [d for d in deps if d not in kept]
            repairs.append(f"{task['id']}: dropped unresolvable dependencies "
                           f"{', '.join(map(str, dropped))}")
        task["depends_on"] = kept

    return repairs
