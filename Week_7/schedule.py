"""
Week 7 — Deterministic scheduling.

The model proposes tasks, effort estimates and dependencies. It does not get
to decide dates. Everything below — topological ordering, the critical path,
resource contention, calendar arithmetic — is computed in Python, because
asking an LLM to add nine working days to a Thursday while respecting two
upstream dependencies is a reliable way to get a plausible wrong answer.

The split matters: the LLM contributes domain judgement (what work exists,
roughly how big it is), and the code contributes arithmetic that is correct
by construction.
"""

from __future__ import annotations

from datetime import date, timedelta


class ScheduleError(ValueError):
    pass


def add_working_days(start: date, days: float) -> date:
    """Advances `days` working days from `start`, skipping weekends."""
    if days <= 0:
        return start
    remaining = days
    current = start
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:      # Mon-Fri
            remaining -= 1
    return current


def working_days_between(start: date, end: date) -> int:
    days, current = 0, start
    while current < end:
        current += timedelta(days=1)
        if current.weekday() < 5:
            days += 1
    return days


def next_working_day(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def topological_order(tasks: list[dict]) -> list[str]:
    """Orders task ids so every dependency precedes its dependents.

    Raises on a cycle rather than silently dropping tasks — a circular
    dependency in a delivery plan is a real planning error worth surfacing.
    """
    ids = {t["id"] for t in tasks}
    deps = {t["id"]: [d for d in t.get("depends_on", []) if d in ids] for t in tasks}
    indegree = {tid: 0 for tid in ids}
    dependents: dict[str, list[str]] = {tid: [] for tid in ids}

    for tid, dep_list in deps.items():
        for d in dep_list:
            indegree[tid] += 1
            dependents[d].append(tid)

    # Stable queue: preserves the order the model emitted tasks in, so two
    # runs over the same plan produce the same schedule.
    order_index = {t["id"]: i for i, t in enumerate(tasks)}
    ready = sorted([tid for tid, n in indegree.items() if n == 0], key=order_index.get)
    ordered: list[str] = []

    while ready:
        tid = ready.pop(0)
        ordered.append(tid)
        newly_ready = []
        for dep in dependents[tid]:
            indegree[dep] -= 1
            if indegree[dep] == 0:
                newly_ready.append(dep)
        ready.extend(sorted(newly_ready, key=order_index.get))

    if len(ordered) != len(ids):
        stuck = sorted(ids - set(ordered))
        raise ScheduleError(f"circular dependency among tasks: {', '.join(stuck)}")

    return ordered


def build_schedule(tasks: list[dict], start: date, team: dict[str, int]) -> list[dict]:
    """Assigns each task a start and end date.

    A task may begin once (a) every dependency has finished, and (b) its role
    has a free pair of hands. `team` maps a role to its headcount, so two
    backend engineers can genuinely run two backend tasks at once.
    """
    by_id = {t["id"]: dict(t) for t in tasks}
    order = topological_order(tasks)
    start = next_working_day(start)

    # Per role, the date each parallel worker next becomes free, and who they
    # were last working on. The latter turns queueing into an explicit
    # predecessor so the critical path can account for resource contention.
    availability: dict[str, list[date]] = {
        role: [start] * max(1, count) for role, count in team.items()
    }
    occupant: dict[str, list[str | None]] = {
        role: [None] * max(1, count) for role, count in team.items()
    }

    scheduled: list[dict] = []
    for tid in order:
        task = by_id[tid]
        role = task.get("role", "Engineer")
        effort = float(task.get("estimate_days", 1) or 1)

        # Constraint (a): dependencies must be finished.
        dep_finish = start
        for dep_id in task.get("depends_on", []):
            if dep_id in by_id and "end" in by_id[dep_id]:
                dep_finish = max(dep_finish, by_id[dep_id]["end"])

        # Constraint (b): somebody in that role must be free. Unknown roles
        # get their own single-person bucket rather than being dropped.
        slots = availability.setdefault(role, [start])
        holders = occupant.setdefault(role, [None] * len(slots))
        earliest_slot_idx = min(range(len(slots)), key=lambda i: slots[i])
        task_start = next_working_day(max(dep_finish, slots[earliest_slot_idx]))
        task_end = add_working_days(task_start, effort)

        # If this task had to wait for a person rather than a dependency, the
        # task that person was finishing is effectively a predecessor.
        previous = holders[earliest_slot_idx]
        task["resource_pred"] = (
            previous if previous and slots[earliest_slot_idx] > dep_finish else None
        )

        slots[earliest_slot_idx] = task_end
        holders[earliest_slot_idx] = tid
        task["start"], task["end"] = task_start, task_end
        by_id[tid] = task
        scheduled.append(task)

    return [by_id[t["id"]] for t in tasks]


def mark_critical_path(tasks: list[dict]) -> list[dict]:
    """Flags tasks with zero slack — the chain that sets the delivery date.

    Backward pass: a task's latest acceptable finish is the earliest start of
    anything depending on it. Where that equals its actual finish, any slip
    moves the whole project.

    Resource contention counts as a dependency here. Textbook CPM walks the
    dependency graph alone, which on a capacity-constrained plan reports slack
    that does not exist: if one engineer must finish A before starting B, then
    A slipping delays B whether or not the graph says so. Including the
    queueing edges makes this the critical *chain* — what the schedule above
    actually implies.
    """
    by_id = {t["id"]: t for t in tasks}
    if not tasks:
        return tasks

    project_end = max(t["end"] for t in tasks)
    latest_finish = {t["id"]: project_end for t in tasks}

    dependents: dict[str, list[str]] = {t["id"]: [] for t in tasks}
    for t in tasks:
        for dep in t.get("depends_on", []):
            if dep in dependents:
                dependents[dep].append(t["id"])
        resource_pred = t.get("resource_pred")
        if resource_pred and resource_pred in dependents:
            dependents[resource_pred].append(t["id"])

    for tid in reversed(topological_order(tasks)):
        for child in dependents[tid]:
            latest_finish[tid] = min(latest_finish[tid], by_id[child]["start"])

    for t in tasks:
        slack = working_days_between(t["end"], latest_finish[t["id"]])
        t["slack_days"] = max(0, slack)
        t["critical"] = t["slack_days"] == 0

    return tasks


def summarise(tasks: list[dict], team: dict[str, int]) -> dict:
    """Project-level totals derived from the scheduled tasks."""
    if not tasks:
        return {"task_count": 0}

    start = min(t["start"] for t in tasks)
    end = max(t["end"] for t in tasks)
    effort = sum(float(t.get("estimate_days", 0) or 0) for t in tasks)
    duration = working_days_between(start, end)

    by_role: dict[str, float] = {}
    for t in tasks:
        by_role[t.get("role", "Engineer")] = (
            by_role.get(t.get("role", "Engineer"), 0) + float(t.get("estimate_days", 0) or 0)
        )

    return {
        "task_count": len(tasks),
        "start": start,
        "end": end,
        "duration_working_days": duration,
        "duration_weeks": round(duration / 5, 1),
        "total_effort_days": round(effort, 1),
        "critical_task_count": sum(1 for t in tasks if t.get("critical")),
        "headcount": sum(team.values()),
        "effort_by_role": {k: round(v, 1) for k, v in sorted(by_role.items())},
        # Serial effort vs elapsed time: how much the team size is actually buying.
        "parallelism": round(effort / duration, 2) if duration else 0.0,
    }
