# RAG Accuracy Report — Week 4

**Zynxis Agentic AI Internship — RAG for Agents**
**Author:** Faozan Mujtaba

## 1. Setup

**Knowledge base:** 3 PDFs from earlier weeks' own deliverables (Week 1's
`logic_flow_diagram.pdf`, Week 3's `tech_note.pdf` and
`architecture_diagram.pdf`) — 5 pages total. Reusing known documents means
every ground-truth fact used below is independently verifiable against the
source PDF.

**Ingestion (`ingest.py`):** each PDF page is extracted with `pypdf`, then
split into ~120-word chunks with a 20-word overlap. 12 chunks were produced
from the 5 source pages.

**Retrieval (`rag.py`):** ChromaDB's default embedding function, top-k=4
nearest chunks by similarity, injected into the prompt as labeled
`[source p.N]` context blocks. The model (Groq `llama-3.3-70b-versatile`) is
instructed to answer only from that context and to cite its source.

## 2. Methodology

Each of 10 test questions is scored on two independent axes:

- **Retrieval accuracy** — did the expected source PDF appear anywhere in
  the top-4 retrieved chunks?
- **Generation accuracy** — does the final answer contain every expected
  keyword (case-insensitive substring match)?

This separates "did we fetch the right passage" from "did the model use it
correctly," which a single pass/fail score would hide.

## 3. Results

```
 #  Retrieval  Generation  Question
 1     PASS       PASS     Long-term memory vector DB + persist path
 2     PASS       PASS     Why ChromaDB over Pinecone
 3     PASS       PASS     Short-term buffer size (N turns)
 4     PASS       PASS     Suggested fix for stale-fact relevance
 5     PASS       PASS     LLM model in the architecture diagram
 6     PASS       PASS     Zebra puzzle: animal Bob owns
 7     PASS       PASS     Zebra puzzle: Alice's house color
 8     PASS       PASS     CoT's typical failure mode
 9     PASS       PASS     Does CoT use external tools
10     PASS       PASS     What "ReAct = ?" per the Key Insight box
```

**Retrieval accuracy: 10/10 (100%)**
**Generation accuracy: 10/10 (100%)**

Full transcripts (question, retrieved chunks, generated answer) are in
`eval_results.json`, produced by running `python eval.py --json
eval_results.json` against the live pipeline.

## 4. Observations & limitations

- A perfect score reflects the benchmark's scale, not a claim that this
  pipeline is error-free at production scale: n=10 questions over a 5-page,
  12-chunk corpus is small enough that top-4 retrieval essentially always
  surfaces the right page.
- Keyword substring matching is a strict, cheap, and reproducible proxy for
  correctness — it doesn't need an LLM judge — but it doesn't verify
  reasoning quality on more open-ended questions. Longer answers with
  paraphrased facts (e.g. "the failure mode is generating incorrect text
  mid-reasoning" instead of the literal word "hallucination") would be
  marked wrong even if substantively correct.
- The real stress test for this pipeline would be a much larger, less
  redundant corpus (dozens of pages covering overlapping topics), where
  chunk boundaries and top-k choice start to matter for retrieval accuracy.
  That's a natural next step beyond this week's scope.
