# Week 2 — Tool Use & Function Calling

**Task:** Build a "Weather & News Agent" that uses an LLM's native function-calling API to fetch real-time data and answer complex queries.

## What This Demonstrates

| Concept | How it's shown |
|---|---|
| Function / tool calling | Groq returns structured `tool_call` objects; we execute and feed results back |
| Multi-tool queries | Agent calls `get_weather` + `get_news` in the same turn when needed |
| Real-time data | Live weather via [wttr.in](https://wttr.in) and news via [HN Algolia](https://hn.algolia.com/api) |
| Tool result injection | Results go back via the `"tool"` role in message history |

### Week 1 vs Week 2

| | Week 1 (ReAct) | Week 2 (Function Calling) |
|---|---|---|
| Tool selection | LLM writes `Action: tool[input]` in text, we regex-parse it | LLM returns structured `tool_call` JSON objects |
| Result injection | String appended to prompt | `{"role": "tool", "tool_call_id": ...}` message |
| Multi-tool support | One tool per step | Multiple tools per turn |

## Setup

```bash
cd Week_2
python -m venv venv
source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

The `.env` file already contains your `GROQ_API_KEY` (same as Week 1).

## Run

```bash
# Demo mode + interactive REPL
python agent.py

# Single query
python agent.py -q "What's the weather in Paris and what's the latest AI news?"
```

## APIs Used

| Tool | API | Auth |
|---|---|---|
| `get_weather` | [wttr.in](https://wttr.in) JSON endpoint | None — completely free |
| `get_news` | [HN Algolia](https://hn.algolia.com/api/v1) search | None — completely free |

## Files

```
Week_2/
├── agent.py        # LLM orchestration loop + tool dispatch
├── tools.py        # Tool implementations + JSON schemas for Groq
├── .env            # GROQ_API_KEY
├── requirements.txt
└── README.md
```
