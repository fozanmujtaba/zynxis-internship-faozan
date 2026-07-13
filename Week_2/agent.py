"""
Week 2 — Tool Use & Function Calling
Weather & News Agent using Groq's native function-calling API.

How this differs from Week 1 (ReAct with string parsing):
  Week 1: manually parsed "Action: tool[input]" from LLM text output
  Week 2: Groq returns structured tool_call objects — the LLM natively decides
          which function to call and with what arguments (JSON). We execute and
          return results via the "tool" role in the message history.

Run modes:
  python agent.py           → runs three demo queries then drops into REPL
  python agent.py -q "..."  → runs a single query and exits
"""

import os
import sys
import json
import groq
from groq import Groq
from dotenv import load_dotenv
from tools import TOOL_SCHEMAS, TOOL_DISPATCH

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL  = "llama-3.3-70b-versatile"

# ── Colours ────────────────────────────────────────────────────────────────────
CYAN   = "\033[96m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
PURPLE = "\033[1m\033[95m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

SYSTEM_PROMPT = """\
You are a helpful Weather & News Agent with access to two real-time tools:
  - get_weather: fetches live weather data for any city worldwide
  - get_news:    searches recent news/tech articles on any topic

When the user asks a question:
1. Identify which tool(s) are needed (you may call more than one).
2. Call them — do NOT guess or fabricate data.
3. Synthesise the tool results into a clear, concise answer.

For multi-part questions (e.g. weather + news), call all required tools before answering.\
"""

DEMO_QUERIES = [
    "What's the weather right now in Tokyo?",
    "What's the latest news on artificial intelligence?",
    "What's the weather in London, and what are the top tech stories today?",
]

# ── Core agent loop ────────────────────────────────────────────────────────────

def call_tool(name: str, args: dict) -> str:
    fn = TOOL_DISPATCH.get(name)
    if not fn:
        return json.dumps({"error": f"Unknown tool: {name}"})
    return json.dumps(fn(**args), indent=2)


def run_agent(user_query: str) -> None:
    print(f"\n{CYAN}User:{RESET} {user_query}")
    print("─" * 60)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_query},
    ]

    while True:
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
            )
        except groq.APIStatusError as e:
            print(f"{PURPLE}Agent:{RESET} Sorry, the model failed to generate a valid tool call ({e.body.get('error', {}).get('code', 'error') if isinstance(e.body, dict) else 'error'}). Please try rephrasing.")
            break

        choice      = response.choices[0]
        msg         = choice.message
        finish      = choice.finish_reason

        # ── The model wants to call one or more tools ──────────────────────────
        if finish == "tool_calls":
            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments)

                print(f"{YELLOW}[Tool Call]  {RESET}{name}({json.dumps(args)})")
                result = call_tool(name, args)

                # pretty-print a short preview of the result
                preview = result[:300] + ("…" if len(result) > 300 else "")
                print(f"{GREEN}[Tool Result]{RESET}\n{preview}\n")

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      result,
                })

        # ── The model has a final answer ───────────────────────────────────────
        else:
            print(f"{PURPLE}Agent:{RESET} {msg.content or '(no response)'}")
            break


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\n{BOLD}Weather & News Agent — Week 2: Tool Use & Function Calling{RESET}")
    print("=" * 60)
    print(f"Model : {MODEL}")
    print(f"Tools : get_weather (wttr.in)  |  get_news (Hacker News)")
    print("=" * 60)

    # Single-query mode: python agent.py -q "..."
    if len(sys.argv) == 3 and sys.argv[1] == "-q":
        run_agent(sys.argv[2])
        return

    # Demo mode: run preset queries
    print(f"\n{BOLD}--- Demo Queries ---{RESET}")
    for query in DEMO_QUERIES:
        run_agent(query)

    # Interactive REPL
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
        run_agent(query)


if __name__ == "__main__":
    main()
