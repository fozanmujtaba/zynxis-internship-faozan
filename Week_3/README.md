# Week 3 — Memory & State Management

**Task:** Build a "Personal Assistant" with short-term (conversation) and long-term (vector DB) memory.

## What This Demonstrates

| Concept | How it's shown |
|---|---|
| Short-term memory | Rolling buffer of the last N turns, injected verbatim as chat history |
| Long-term memory | Every user statement is embedded and stored in ChromaDB; recalled by similarity search on each new turn |
| Recall beyond the context window | The demo asks about a fact from turn 1 *after* it has scrolled out of the short-term buffer — the assistant still answers correctly via long-term recall |
| Persistence | ChromaDB is a `PersistentClient` writing to `./chroma_store/`, so memories survive across process restarts |

## Architecture

```
User query
    │
    ├──► LongTermMemory.recall(query)  ── ChromaDB similarity search ──► top-k past facts
    │
    ├──► ShortTermMemory.as_messages() ── last N turns verbatim
    │
    ▼
[system prompt] + [recalled memories] + [short-term buffer] + [new query] ──► Groq LLM ──► answer
    │
    ▼
ShortTermMemory.add(...)     (buffer updated, oldest turn evicted if over capacity)
LongTermMemory.remember(...) (new fact embedded and stored permanently)
```

See [architecture_diagram.pdf](architecture_diagram.pdf) and [tech_note.pdf](tech_note.pdf) for the full write-up.

## Setup

```bash
cd Week_3
python -m venv venv
source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

The `.env` file already contains `GROQ_API_KEY` (same key as Week 1/2).

## Run

```bash
# Demo (long-term recall past the short-term window) + interactive REPL
python assistant.py

# Wipe long-term memory first, then run
python assistant.py --reset

# Single query
python assistant.py -q "What's my favorite programming language?"
```

## Files

```
Week_3/
├── assistant.py             # Agent loop: recall → respond → remember
├── memory.py                # ShortTermMemory (buffer) + LongTermMemory (ChromaDB)
├── generate_diagram.py       # Builds architecture_diagram.pdf
├── tech_note.md               # Source for the 2-page technical note
├── generate_tech_note.py     # Renders tech_note.md → tech_note.pdf
├── architecture_diagram.pdf   # Deliverable: memory architecture diagram
├── tech_note.pdf              # Deliverable: 2-page technical note
├── chroma_store/              # ChromaDB's on-disk vector index (generated at runtime)
├── .env                        # GROQ_API_KEY
├── requirements.txt
└── README.md
```
