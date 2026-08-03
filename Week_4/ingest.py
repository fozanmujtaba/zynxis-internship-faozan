"""
Week 4 — RAG for Agents
PDF ingestion: extract text -> chunk -> embed -> store in ChromaDB.

Run:
  python ingest.py            # ingest every PDF in ./docs
  python ingest.py --reset    # wipe the collection first
"""

import glob
import os
import sys

import chromadb
from pypdf import PdfReader

DOCS_DIR     = "docs"
PERSIST_DIR  = "./chroma_store"
COLLECTION   = "week4_rag"
CHUNK_WORDS  = 120
CHUNK_OVERLAP = 20


def extract_pages(pdf_path: str) -> list[str]:
    reader = PdfReader(pdf_path)
    return [page.extract_text() or "" for page in reader.pages]


def chunk_text(text: str, chunk_words: int = CHUNK_WORDS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks = []
    step = chunk_words - overlap
    for start in range(0, len(words), step):
        chunk = " ".join(words[start:start + chunk_words])
        if chunk:
            chunks.append(chunk)
        if start + chunk_words >= len(words):
            break
    return chunks


def ingest(collection) -> int:
    pdf_paths = sorted(glob.glob(os.path.join(DOCS_DIR, "*.pdf")))
    if not pdf_paths:
        print(f"No PDFs found in ./{DOCS_DIR}")
        return 0

    total_chunks = 0
    for pdf_path in pdf_paths:
        source = os.path.basename(pdf_path)
        pages = extract_pages(pdf_path)

        for page_num, page_text in enumerate(pages, start=1):
            chunks = chunk_text(page_text)
            if not chunks:
                continue

            ids = [f"{source}::p{page_num}::c{i}" for i in range(len(chunks))]
            metadatas = [{"source": source, "page": page_num, "chunk": i} for i in range(len(chunks))]

            collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
            total_chunks += len(chunks)

        print(f"Ingested {source}: {len(pages)} page(s)")

    return total_chunks


def main() -> None:
    client = chromadb.PersistentClient(path=PERSIST_DIR)

    if "--reset" in sys.argv:
        try:
            client.delete_collection(COLLECTION)
        except Exception:
            pass
        print("Cleared existing collection.")

    collection = client.get_or_create_collection(COLLECTION)
    total = ingest(collection)
    print(f"\nTotal chunks stored: {total}")
    print(f"Collection '{COLLECTION}' now has {collection.count()} chunks.")


if __name__ == "__main__":
    main()
