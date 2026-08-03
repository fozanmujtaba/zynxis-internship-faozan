"""Interaction logging for the Week 5 multi-agent crew.

CrewAI prints its agent chatter to stdout; that's readable but not a
deliverable. This module captures two things side by side:

  - the raw verbose stdout of every crew run    -> crew_verbose.log
  - a structured record of each agent handoff   -> interaction_log.json
                                                -> interaction_log.md

The structured log is what makes the "who did what, in what order" story
legible without reading thousands of lines of ANSI-coloured output.
"""

import io
import json
import re
import sys
import time
from contextlib import contextmanager
from datetime import datetime

ANSI = re.compile(r"\033\[[0-9;]*m")


class Tee(io.TextIOBase):
    """Writes to the real stdout and a buffer at the same time."""

    def __init__(self, stream, buffer: io.StringIO):
        self.stream = stream
        self.buffer = buffer

    def write(self, text: str) -> int:
        self.stream.write(text)
        self.buffer.write(text)
        return len(text)

    def flush(self) -> None:
        self.stream.flush()


@contextmanager
def capture_stdout():
    """Yields a StringIO that mirrors everything printed inside the block."""
    buffer = io.StringIO()
    original = sys.stdout
    sys.stdout = Tee(original, buffer)
    try:
        yield buffer
    finally:
        sys.stdout = original


class RunLog:
    """Accumulates structured agent-interaction records across a whole run."""

    def __init__(self, topic: str):
        self.topic = topic
        self.started_at = datetime.now()
        self.events: list[dict] = []
        self.verbose_chunks: list[str] = []

    def record(self, phase: str, agent: str, task: str, output: str, seconds: float) -> None:
        self.events.append(
            {
                "n": len(self.events) + 1,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "phase": phase,
                "agent": agent,
                "task": task,
                "seconds": round(seconds, 2),
                "output_chars": len(output),
                "output": output,
            }
        )

    def add_verbose(self, text: str) -> None:
        self.verbose_chunks.append(ANSI.sub("", text))

    # -- outputs -------------------------------------------------------

    def write_json(self, path: str) -> None:
        payload = {
            "topic": self.topic,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "total_seconds": round(self.elapsed(), 2),
            "event_count": len(self.events),
            "events": self.events,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def write_verbose(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(self.verbose_chunks))

    def write_markdown(self, path: str) -> None:
        lines = [
            "# Agent Interaction Log — Week 5",
            "",
            f"**Topic:** {self.topic}  ",
            f"**Run started:** {self.started_at.strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"**Total agent turns:** {len(self.events)}  ",
            f"**Wall-clock time:** {self.elapsed():.1f}s",
            "",
            "## Handoff sequence",
            "",
            "| # | Phase | Agent | Task | Time (s) | Output (chars) |",
            "|---|---|---|---|---|---|",
        ]
        for e in self.events:
            lines.append(
                f"| {e['n']} | {e['phase']} | {e['agent']} | {e['task']} "
                f"| {e['seconds']} | {e['output_chars']} |"
            )

        lines += ["", "## Turn-by-turn output", ""]
        for e in self.events:
            lines += [
                f"### Turn {e['n']} — {e['agent']} · {e['task']}",
                "",
                f"*Phase: {e['phase']} · {e['seconds']}s · {e['output_chars']} chars*",
                "",
                "```",
                e["output"].strip(),
                "```",
                "",
            ]

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def elapsed(self) -> float:
        return (datetime.now() - self.started_at).total_seconds()


@contextmanager
def timed():
    """Yields a one-element list that receives the elapsed seconds."""
    holder = [0.0]
    start = time.time()
    try:
        yield holder
    finally:
        holder[0] = time.time() - start


def make_recorder(log: RunLog, phase: str, agent: str, task: str, clock: list[float]):
    """Builds a CrewAI task callback that logs the turn when the task finishes.

    CrewAI runs every task of a crew inside one kickoff() call, so wall-clock
    timing around kickoff can only give a total. Hooking each Task's own
    completion callback instead gives a real per-agent duration: `clock` holds
    the moment the previous task ended, so each turn is measured from there.
    """

    def record(output) -> None:
        now = time.time()
        log.record(phase, agent, task, str(output), now - clock[0])
        clock[0] = now

    return record
