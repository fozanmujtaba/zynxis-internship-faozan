# Week 1 — Prompt Engineering & ReAct

**Intern:** Faozan Mujtaba  
**Discipline:** Agentic AI & Autonomous Systems  
**Topic:** Chain-of-Thought (CoT) and ReAct (Reason + Act) Prompting

---

## Overview

This week covers two foundational prompting patterns used in agentic AI systems:

| Pattern | What it does |
|---------|-------------|
| **Chain-of-Thought (CoT)** | Forces the LLM to reason step-by-step before giving an answer |
| **ReAct** | Interleaves reasoning (Thought) with tool calls (Action) and results (Observation) in a loop |

---

## Files

| File | Description |
|------|-------------|
| `cot_prompting.py` | Compares zero-shot vs CoT on a multi-step train puzzle |
| `react_agent.py` | Manual ReAct loop with `calculator` and `lookup` tools |
| `logic_flow_diagram.pdf` | Architecture diagram of both patterns |
| `requirements.txt` | Python dependencies |

---

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Add your API key
echo "ANTHROPIC_API_KEY=your_key_here" > .env
```

Get your API key at: https://console.anthropic.com

---

## Running the Scripts

```bash
# Chain-of-Thought demo
python cot_prompting.py

# ReAct agent demo
python react_agent.py
```

---

## How It Works

### Chain-of-Thought (CoT)

Standard prompt → model jumps to an answer, often wrong on multi-step problems.

CoT prompt → model is guided to show every reasoning step first:

```
Step 1: Calculate how long Train A travels before Train B departs...
Step 2: Set up equations for when they meet...
Answer: They meet at 10:20 AM, 132 miles from City A.
```

### ReAct Loop

```
Thought: I need the speed of light to solve part (a).
Action: lookup[speed of light]
Observation: 299792458 meters per second

Thought: Earth circumference is needed. Let me look it up.
Action: lookup[earth circumference]
Observation: 40075 kilometers

Thought: Convert km to meters, then divide by speed of light.
Action: calculator[40075 * 1000 / 299792458]
Observation: 0.133564

Answer: Light takes ~0.1336 seconds to circle the Earth once.
```

The agent never guesses — every number is computed or looked up via a tool.

---

## Key Concepts

- **Zero-shot prompting**: Ask the question directly, no guidance on how to reason
- **Chain-of-Thought**: Add "step by step" or "show your work" to trigger explicit reasoning
- **ReAct**: Combine reasoning with tool use in a Thought → Action → Observation loop
- **Stop sequences**: Used to pause the LLM at `Observation:` so the Python code can inject the real tool result
