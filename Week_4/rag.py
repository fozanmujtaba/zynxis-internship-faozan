"""
Week 4 — RAG for Agents
Retrieval-Augmented Generation over the ingested PDF knowledge base.

Run modes:
  python rag.py            → demo queries + interactive REPL
  python rag.py -q "..."   → single query and exit
"""

import os
import sys

import chromadb
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"

PERSIST_DIR = "./chroma_store"
COLLECTION  = "week4_rag"
TOP_K       = 4

CYAN   = "\033[96m"
YELLOW = "\033[93m"
PURPLE = "\033[1m\033[95m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

SYSTEM_PROMPT = """\
You are a RAG-based assistant. Answer the user's question using ONLY the
provided context chunks below — do not use outside knowledge. If the context
doesn't contain the answer, say so explicitly instead of guessing.

Cite which source file each fact came from.\
"""

_chroma = chromadb.PersistentClient(path=PERSIST_DIR)
_collection = _chroma.get_or_create_collection(COLLECTION)


def retrieve(query: str, k: int = TOP_K) -> list[dict]:
    if _collection.count() == 0:
        return []
    n = min(k, _collection.count())
    results = _collection.query(query_texts=[query], n_results=n)
    hits = []
    for doc, meta, dist in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
        hits.append({"text": doc, "source": meta["source"], "page": meta["page"], "distance": dist})
    return hits


def build_context(hits: list[dict]) -> str:
    blocks = []
    for h in hits:
        blocks.append(f"[{h['source']} p.{h['page']}]\n{h['text']}")
    return "\n\n".join(blocks)


def answer(query: str, k: int = TOP_K, verbose: bool = True) -> dict:
    hits = retrieve(query, k)

    if verbose:
        print(f"\n{CYAN}Query:{RESET} {query}")
        if hits:
            print(f"{YELLOW}[Retrieved]{RESET}")
            for h in hits:
                print(f"  - {h['source']} (p.{h['page']}, dist={h['distance']:.3f})")
        else:
            print(f"{YELLOW}[Retrieved]{RESET} nothing — has ingest.py been run?")

    if not hits:
        response_text = "I don't have any ingested documents to answer from. Run ingest.py first."
    else:
        context = build_context(hits)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": f"Context:\n{context}"},
            {"role": "user", "content": query},
        ]
        response = client.chat.completions.create(model=MODEL, messages=messages)
        response_text = response.choices[0].message.content

    if verbose:
        print(f"{PURPLE}Answer:{RESET} {response_text}")

    return {"query": query, "answer": response_text, "sources": [h["source"] for h in hits]}


DEMO_QUERIES = [
    "What vector database backs the Week 3 personal assistant's long-term memory, and where does it persist data?",
    "In the Week 1 Zebra puzzle, which animal does Bob own?",
    "According to the CoT vs ReAct comparison table, what is CoT's typical failure mode?",
]


def main() -> None:
    print(f"\n{BOLD}RAG Pipeline — Week 4: RAG for Agents{RESET}")
    print("=" * 60)
    print(f"Model      : {MODEL}")
    print(f"Vector DB  : ChromaDB ({PERSIST_DIR}, collection='{COLLECTION}')")
    print(f"Documents  : {_collection.count()} chunks ingested")
    print("=" * 60)

    if len(sys.argv) == 3 and sys.argv[1] == "-q":
        answer(sys.argv[2])
        return

    print(f"\n{BOLD}--- Demo Queries ---{RESET}")
    for q in DEMO_QUERIES:
        answer(q)

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
        answer(query)


if __name__ == "__main__":
    main()
