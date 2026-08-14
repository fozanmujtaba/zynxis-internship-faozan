"""
A resilient Groq client.

Week 5 of this internship lost a report section to an unhandled 429 partway
through a long run. Everything here exists because of that failure:

  - retries with exponential backoff and jitter, honouring Retry-After
  - a circuit breaker, so a hard daily quota stops the run cleanly instead of
    grinding through twenty more doomed requests
  - a content-addressed disk cache, so re-auditing an unchanged file is free
  - token accounting, so the cost of a run is a number rather than a surprise

The audit degrades to static-analysis-only if the model is unreachable. A
code auditor that produces nothing when an API is down is not much of an
auditor.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
from pathlib import Path

from groq import Groq
from dotenv import load_dotenv

load_dotenv()

MODEL = "llama-3.3-70b-versatile"
CACHE_DIR = Path(".audit_cache")

MAX_ATTEMPTS = 4
BASE_DELAY = 2.0
MAX_DELAY = 30.0
CIRCUIT_BREAK_AFTER = 2      # consecutive quota failures before giving up


class LLMUnavailable(RuntimeError):
    """Raised when the model cannot be reached and the audit must degrade."""


class LLMClient:
    def __init__(self, use_cache: bool = True, model: str = MODEL):
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise LLMUnavailable("GROQ_API_KEY is not set")
        self._client = Groq(api_key=key)
        self.model = model
        self.use_cache = use_cache
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.calls = 0
        self.cache_hits = 0
        self.retries = 0
        self._consecutive_quota_failures = 0
        if use_cache:
            CACHE_DIR.mkdir(exist_ok=True)

    # -- cache --------------------------------------------------------

    def _cache_path(self, payload: str) -> Path:
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
        return CACHE_DIR / f"{digest}.json"

    def _read_cache(self, payload: str) -> str | None:
        if not self.use_cache:
            return None
        path = self._cache_path(payload)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))["response"]
            except (json.JSONDecodeError, KeyError, OSError):
                return None
        return None

    def _write_cache(self, payload: str, response: str) -> None:
        if not self.use_cache:
            return
        try:
            self._cache_path(payload).write_text(
                json.dumps({"response": response}), encoding="utf-8")
        except OSError:
            pass          # a cache that cannot be written is not a fatal error

    # -- request ------------------------------------------------------

    def complete(self, system: str, user: str, *, json_mode: bool = False,
                 temperature: float = 0.2) -> str:
        payload = json.dumps(
            {"m": self.model, "s": system, "u": user, "j": json_mode, "t": temperature},
            sort_keys=True)

        cached = self._read_cache(payload)
        if cached is not None:
            self.cache_hits += 1
            return cached

        if self._consecutive_quota_failures >= CIRCUIT_BREAK_AFTER:
            raise LLMUnavailable(
                "circuit breaker open: repeated quota failures, abandoning LLM review")

        kwargs = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        last_error: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self._client.chat.completions.create(**kwargs)
            except Exception as exc:                      # noqa: BLE001
                last_error = exc
                if not _is_retryable(exc) or attempt == MAX_ATTEMPTS:
                    break
                delay = _backoff(attempt, exc)
                self.retries += 1
                print(f"    retry {attempt}/{MAX_ATTEMPTS - 1} in {delay:.1f}s "
                      f"({_short(exc)})")
                time.sleep(delay)
                continue

            usage = getattr(response, "usage", None)
            if usage:
                self.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
                self.completion_tokens += getattr(usage, "completion_tokens", 0) or 0
            self.calls += 1
            self._consecutive_quota_failures = 0

            text = response.choices[0].message.content or ""
            self._write_cache(payload, text)
            return text

        if last_error is not None and _is_quota(last_error):
            self._consecutive_quota_failures += 1
        raise LLMUnavailable(f"request failed after {MAX_ATTEMPTS} attempts: "
                             f"{_short(last_error)}")

    # -- reporting ----------------------------------------------------

    def usage(self) -> dict:
        return {
            "model": self.model,
            "api_calls": self.calls,
            "cache_hits": self.cache_hits,
            "retries": self.retries,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
        }


def _short(exc: Exception | None) -> str:
    if exc is None:
        return "unknown error"
    text = str(exc).replace("\n", " ")
    return text[:140] + ("…" if len(text) > 140 else "")


def _status_of(exc: Exception) -> int | None:
    return getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None)


def _is_quota(exc: Exception) -> bool:
    return _status_of(exc) == 429 or "rate_limit" in str(exc).lower()


def _is_retryable(exc: Exception) -> bool:
    status = _status_of(exc)
    if status in (429, 500, 502, 503, 504):
        return True
    text = str(exc).lower()
    return any(s in text for s in ("timeout", "connection", "temporarily"))


def _backoff(attempt: int, exc: Exception) -> float:
    """Exponential backoff with jitter, capped, honouring Retry-After."""
    retry_after = getattr(getattr(exc, "response", None), "headers", {}) or {}
    try:
        if hinted := retry_after.get("retry-after"):
            return min(float(hinted), MAX_DELAY)
    except (TypeError, ValueError):
        pass
    # Jitter stops parallel workers retrying in lockstep.
    return min(BASE_DELAY * (2 ** (attempt - 1)), MAX_DELAY) * (0.5 + random.random() / 2)
