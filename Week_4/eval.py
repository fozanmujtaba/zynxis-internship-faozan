"""
Week 4 — RAG for Agents
Accuracy evaluation harness: runs a fixed QA set through the RAG pipeline and
scores both retrieval (did we fetch the right source?) and generation (does
the answer contain the expected fact?).

Run:
  python eval.py             # prints per-question results + summary
  python eval.py --json out.json   # also dump raw results as JSON
"""

import json
import sys

from rag import answer as rag_answer

# Each entry: question, keywords that must all appear (case-insensitive) in
# the generated answer for it to count as correct, and the source PDF the
# supporting fact actually lives in (for retrieval scoring).
QA_SET = [
    {
        "question": "What vector database does the Week 3 personal assistant use for long-term memory, and what local directory does it persist to?",
        "expect_keywords": ["chromadb", "chroma_store"],
        "expect_source": "week3_tech_note.pdf",
    },
    {
        "question": "Why was ChromaDB chosen over Pinecone for the Week 3 project?",
        "expect_keywords": ["api key"],
        "expect_source": "week3_tech_note.pdf",
    },
    {
        "question": "How many turns does the Week 3 short-term memory buffer hold in the demo?",
        "expect_keywords": ["3"],
        "expect_source": "week3_tech_note.pdf",
    },
    {
        "question": "What extension does the Week 3 tech note suggest to stop stale facts from outliving their relevance?",
        "expect_keywords": ["expiry"],
        "expect_source": "week3_tech_note.pdf",
    },
    {
        "question": "In the Week 3 architecture diagram, which LLM model powers the personal assistant?",
        "expect_keywords": ["llama-3.3-70b"],
        "expect_source": "week3_architecture_diagram.pdf",
    },
    {
        "question": "In the Week 1 Zebra puzzle example, which animal does Bob own according to the final answer?",
        "expect_keywords": ["fish"],
        "expect_source": "week1_logic_flow_diagram.pdf",
    },
    {
        "question": "What color house does Alice live in, per Clue 1 in the Week 1 logic flow diagram?",
        "expect_keywords": ["red"],
        "expect_source": "week1_logic_flow_diagram.pdf",
    },
    {
        "question": "According to the Week 1 CoT vs ReAct comparison table, what is the typical failure mode of Chain-of-Thought reasoning?",
        "expect_keywords": ["hallucination"],
        "expect_source": "week1_logic_flow_diagram.pdf",
    },
    {
        "question": "Does Chain-of-Thought reasoning use external tools, per the Week 1 comparison table?",
        "expect_keywords": ["none"],
        "expect_source": "week1_logic_flow_diagram.pdf",
    },
    {
        "question": "What does the Week 1 Key Insight box say ReAct equals?",
        "expect_keywords": ["cot", "tool use"],
        "expect_source": "week1_logic_flow_diagram.pdf",
    },
]


def score_one(qa: dict) -> dict:
    result = rag_answer(qa["question"], verbose=False)
    answer_lower = result["answer"].lower()

    keyword_hits = [kw for kw in qa["expect_keywords"] if kw.lower() in answer_lower]
    generation_correct = len(keyword_hits) == len(qa["expect_keywords"])
    retrieval_correct = qa["expect_source"] in result["sources"]

    return {
        "question": qa["question"],
        "answer": result["answer"],
        "sources_retrieved": result["sources"],
        "expect_source": qa["expect_source"],
        "expect_keywords": qa["expect_keywords"],
        "retrieval_correct": retrieval_correct,
        "generation_correct": generation_correct,
    }


def main() -> None:
    results = [score_one(qa) for qa in QA_SET]

    n = len(results)
    retrieval_acc = sum(r["retrieval_correct"] for r in results) / n
    generation_acc = sum(r["generation_correct"] for r in results) / n

    for i, r in enumerate(results, start=1):
        ret_mark = "PASS" if r["retrieval_correct"] else "FAIL"
        gen_mark = "PASS" if r["generation_correct"] else "FAIL"
        print(f"\nQ{i}: {r['question']}")
        print(f"  Answer     : {r['answer']}")
        print(f"  Retrieval  : [{ret_mark}] expected '{r['expect_source']}', got {r['sources_retrieved']}")
        print(f"  Generation : [{gen_mark}] expected keywords {r['expect_keywords']}")

    print("\n" + "=" * 60)
    print(f"Retrieval accuracy  : {retrieval_acc:.0%} ({sum(r['retrieval_correct'] for r in results)}/{n})")
    print(f"Generation accuracy : {generation_acc:.0%} ({sum(r['generation_correct'] for r in results)}/{n})")

    if "--json" in sys.argv:
        out_path = sys.argv[sys.argv.index("--json") + 1]
        with open(out_path, "w") as f:
            json.dump({
                "results": results,
                "retrieval_accuracy": retrieval_acc,
                "generation_accuracy": generation_acc,
            }, f, indent=2)
        print(f"\nWrote raw results to {out_path}")


if __name__ == "__main__":
    main()
