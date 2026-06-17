"""
Week 1 — ReAct (Reason + Act) Agent Demo

Implements the ReAct loop manually (no framework):
  Thought     → what the agent decides to do next
  Action      → calls a tool with an input
  Observation → the tool result fed back to the agent
  ... repeat until the agent writes "Answer:"

The agent has two tools: calculator and a fact lookup table.
"""

import os
import re
import math
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"

# ── Tools ──────────────────────────────────────────────────────────────────────

def calculator(expression: str) -> str:
    try:
        allowed = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
        result = eval(expression, {"__builtins__": {}}, allowed)
        return str(round(result, 6))
    except Exception as e:
        return f"Error: {e}"


def lookup(query: str) -> str:
    facts = {
        "speed of light":        "299792458 meters per second",
        "speed of sound":        "343 meters per second (in air at 20°C)",
        "earth circumference":   "40075 kilometers",
        "earth radius":          "6371 kilometers",
        "seconds in a day":      "86400",
        "seconds in an hour":    "3600",
        "meters in a kilometer": "1000",
        "pi":                    "3.14159265358979",
    }
    q = query.lower()
    for key, value in facts.items():
        if key in q:
            return value
    return f"No fact found for: '{query}'"


TOOLS = {
    "calculator": calculator,
    "lookup":     lookup,
}

# ── Prompt ─────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a problem-solving agent. Use the tools available to you to solve problems step by step.

Available tools:
  calculator[expression]  — evaluates a math expression (supports +, -, *, /, **, math.sqrt, etc.)
  lookup[query]           — looks up a scientific or numeric fact

Follow this format EXACTLY for every step:
Thought: <what you need to do next and why>
Action: <tool_name>[<input>]
Observation: <tool result will appear here>

Repeat Thought/Action/Observation until you have the final answer, then write:
Thought: I have all the information needed to answer.
Answer: <your complete final answer>

Do NOT guess. Always use a tool to compute or verify numbers."""

PUZZLE = """
If light travels at its known speed, how many seconds does it take to travel:
  (a) once around the Earth's equator?
  (b) from the Earth to the Moon (average distance: 384400 km)?

Show both answers.
"""

# ── ReAct Loop ─────────────────────────────────────────────────────────────────

def run_react(puzzle: str, max_steps: int = 12) -> str:
    full_trace = "Thought:"
    current_prompt = f"{SYSTEM_PROMPT}\n\nQuestion: {puzzle}\n\nThought:"

    for step in range(max_steps):
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": current_prompt}],
            max_tokens=512,
            stop=["Observation:"],
        )

        llm_output = response.choices[0].message.content
        full_trace += llm_output

        if "Answer:" in llm_output:
            break

        action_match = re.search(r"Action:\s*(\w+)\[(.+?)\]", llm_output)
        if not action_match:
            full_trace += "\nObservation: (no valid action found — stopping)\n"
            break

        tool_name  = action_match.group(1).strip()
        tool_input = action_match.group(2).strip()

        observation = TOOLS[tool_name](tool_input) if tool_name in TOOLS else f"Unknown tool: {tool_name}"

        obs_block = f"\nObservation: {observation}\nThought:"
        full_trace += obs_block
        current_prompt = f"{SYSTEM_PROMPT}\n\nQuestion: {puzzle}\n\n{full_trace}"

    return full_trace


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nReAct AGENT DEMO — Reason + Act Loop")
    print(f"\nPuzzle:{PUZZLE}")
    print("-" * 60)

    trace = run_react(PUZZLE)

    for line in trace.splitlines():
        if line.startswith("Thought:"):
            print(f"\n\033[94m{line}\033[0m")
        elif line.startswith("Action:"):
            print(f"\033[93m{line}\033[0m")
        elif line.startswith("Observation:"):
            print(f"\033[92m{line}\033[0m")
        elif line.startswith("Answer:"):
            print(f"\n\033[1m\033[95m{line}\033[0m")
        else:
            print(line)
