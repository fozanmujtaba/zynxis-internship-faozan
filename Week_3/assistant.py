"""
Week 3 — Memory & State Management
Personal Assistant with short-term (rolling buffer) + long-term (ChromaDB) memory.

Why two memory tiers:
  Short-term: the last few turns verbatim, for immediate conversational context.
  Long-term:  every user statement embedded into ChromaDB, so facts survive
              even after they've scrolled out of the short-term buffer.

Run modes:
  python assistant.py           → runs a demo showing long-term recall, then REPL
  python assistant.py -q "..."  → single query and exit
  python assistant.py --reset   → wipes long-term memory store first
"""

import os
import sys

from groq import Groq
from dotenv import load_dotenv

from memory import ShortTermMemory, LongTermMemory

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"

# ── Colours ──────────────────────────────────────────────────────────────────
CYAN   = "\033[96m"
YELLOW = "\033[93m"
PURPLE = "\033[1m\033[95m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

SYSTEM_PROMPT = """\
You are a helpful Personal Assistant with memory of past conversations.

You will be given a "Relevant memories" section containing facts recalled
from long-term storage that may or may not be related to the current
question. Use them only if they're actually relevant — don't force a
connection that isn't there.\
"""

SHORT_TERM_TURNS = 3  # keep last 3 user+assistant pairs verbatim

short_term = ShortTermMemory(max_turns=SHORT_TERM_TURNS)
long_term  = LongTermMemory()


def respond(user_query: str) -> str:
    print(f"\n{CYAN}User:{RESET} {user_query}")

    recalled = long_term.recall(user_query, n_results=3)
    if recalled:
        memory_block = "Relevant memories:\n" + "\n".join(f"- {m}" for m in recalled)
        print(f"{YELLOW}[Long-term recall]{RESET} {recalled}")
    else:
        memory_block = "Relevant memories: (none found)"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": memory_block},
        *short_term.as_messages(),
        {"role": "user", "content": user_query},
    ]

    response = client.chat.completions.create(model=MODEL, messages=messages)
    answer = response.choices[0].message.content

    print(f"{PURPLE}Assistant:{RESET} {answer}")

    short_term.add("user", user_query)
    short_term.add("assistant", answer)
    long_term.remember(user_query, metadata={"role": "user"})

    return answer


DEMO_TURNS = [
    "Hi, I'm Faozan. I'm doing an 8-week Agentic AI internship at Zynxis, and my favorite programming language is Python.",
    "My internship submission deadline is August 16, 2026.",
    "By the way, what's a good analogy for how a transformer's attention mechanism works?",
    "Can you suggest a healthy breakfast that's quick to make on a busy morning?",
    "What's the difference between short-term and long-term memory in an AI agent, in one sentence?",
    "What's my favorite programming language again?",  # by now, turn 1 has scrolled out of the short-term buffer
]


def run_demo() -> None:
    print(f"\n{BOLD}--- Demo: long-term recall beyond the short-term window ---{RESET}")
    print(f"(short-term buffer holds the last {SHORT_TERM_TURNS} turns; turn 1 will fall out of it by turn {SHORT_TERM_TURNS + 2})")
    for turn in DEMO_TURNS:
        respond(turn)


def main() -> None:
    print(f"\n{BOLD}Personal Assistant — Week 3: Memory & State Management{RESET}")
    print("=" * 60)
    print(f"Model      : {MODEL}")
    print(f"Short-term : last {SHORT_TERM_TURNS} turns (in-memory buffer)")
    print(f"Long-term  : ChromaDB (./chroma_store, persists across runs)")
    print("=" * 60)

    if "--reset" in sys.argv:
        long_term.reset()
        print("Long-term memory store cleared.")
        sys.argv.remove("--reset")

    if len(sys.argv) == 3 and sys.argv[1] == "-q":
        respond(sys.argv[2])
        return

    run_demo()

    print(f"\n{BOLD}--- Interactive Mode (type 'quit' to exit) ---{RESET}")
    while True:
        try:
            query = input(f"\n{CYAN}You:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if query.lower() in ("quit", "exit", "q", ""):
            print("Goodbye!")
            break
        respond(query)


if __name__ == "__main__":
    main()
