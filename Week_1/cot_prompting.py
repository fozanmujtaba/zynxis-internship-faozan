"""
Week 1 — Chain-of-Thought (CoT) Prompting Demo

Compares zero-shot vs CoT on a multi-step logic puzzle.
CoT forces the model to reason step-by-step before answering,
which dramatically improves accuracy on complex problems.
"""

import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"

PUZZLE = """
A train leaves City A at 8:00 AM traveling at 60 mph toward City B.
Another train leaves City B at 9:00 AM traveling at 90 mph toward City A.
The distance between City A and City B is 300 miles.

Questions:
1. At what time do the two trains meet?
2. How far from City A is the meeting point?
3. Which train has traveled farther when they meet?
"""

ZERO_SHOT_PROMPT = f"""Solve this puzzle:
{PUZZLE}
"""

COT_PROMPT = f"""Solve this puzzle step by step. Show every calculation clearly before giving the final answer.
{PUZZLE}

Step-by-step solution:"""


def query(prompt: str, max_tokens: int = 1024) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


def divider(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)


if __name__ == "__main__":
    print("\nCHAIN-OF-THOUGHT PROMPTING DEMO")
    print("Puzzle:", PUZZLE)

    divider("ZERO-SHOT (no reasoning guidance)")
    print(query(ZERO_SHOT_PROMPT, max_tokens=256))

    divider("CHAIN-OF-THOUGHT (step-by-step reasoning)")
    print(query(COT_PROMPT, max_tokens=1024))

    divider("OBSERVATION")
    print("Zero-shot prompts the model to jump straight to an answer.")
    print("CoT prompts it to reason through each sub-problem first,")
    print("reducing errors on multi-step arithmetic and logic tasks.")
