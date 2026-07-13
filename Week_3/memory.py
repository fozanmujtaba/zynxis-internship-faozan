"""
Week 3 — Memory & State Management
Short-term (rolling buffer) + long-term (ChromaDB vector store) memory.
"""

import time
import uuid

import chromadb


class ShortTermMemory:
    """Keeps the last N conversation turns verbatim, for immediate context."""

    def __init__(self, max_turns: int = 6):
        self.max_turns = max_turns
        self._buffer: list[dict] = []

    def add(self, role: str, content: str) -> None:
        self._buffer.append({"role": role, "content": content})
        # a "turn" is one user+assistant pair, so cap at 2*max_turns messages
        overflow = len(self._buffer) - (self.max_turns * 2)
        if overflow > 0:
            self._buffer = self._buffer[overflow:]

    def as_messages(self) -> list[dict]:
        return list(self._buffer)

    def clear(self) -> None:
        self._buffer.clear()


class LongTermMemory:
    """Persistent semantic memory backed by a local ChromaDB collection.

    Every stored memory is embedded and can be recalled later by similarity
    search, regardless of how long ago it was said or whether it's still in
    the short-term buffer.
    """

    def __init__(self, persist_dir: str = "./chroma_store", collection: str = "personal_assistant"):
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(collection)

    def remember(self, text: str, metadata: dict | None = None) -> None:
        self._collection.add(
            ids=[str(uuid.uuid4())],
            documents=[text],
            metadatas=[{**(metadata or {}), "timestamp": time.time()}],
        )

    def recall(self, query: str, n_results: int = 3) -> list[str]:
        if self._collection.count() == 0:
            return []
        n_results = min(n_results, self._collection.count())
        results = self._collection.query(query_texts=[query], n_results=n_results)
        return results["documents"][0] if results["documents"] else []

    def reset(self) -> None:
        self._client.delete_collection(self._collection.name)
        self._collection = self._client.get_or_create_collection(self._collection.name)
