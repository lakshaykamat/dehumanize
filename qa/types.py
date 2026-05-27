"""Public types for the qa pipeline."""

from __future__ import annotations

import threading
from typing import Callable, NamedTuple


class QuestionSpec(NamedTuple):
    question: str
    min_words: int
    max_words: int

    @property
    def target_words(self) -> int:
        return (self.min_words + self.max_words) // 2

    @property
    def range_str(self) -> str:
        return f"{self.min_words}-{self.max_words}"


QAPair = tuple[QuestionSpec, str]


class ProgressEvent(NamedTuple):
    """Pipeline event for progress reporting.

    kind:    "start", "attempt", "ok", "retry", "give_up"
    index:   1-based question index
    total:   total number of questions
    spec:    the question spec
    attempt: 1-based attempt number for "attempt" / "retry" / "ok" / "give_up"
    words:   word count of the candidate answer (post-transform), when relevant
    """
    kind: str
    index: int
    total: int
    spec: QuestionSpec
    attempt: int | None = None
    words: int | None = None


ProgressFn = Callable[[ProgressEvent], None]


class MissingAPIKeyError(RuntimeError):
    pass


class TokenUsage:
    """Thread-safe accumulator for OpenAI token usage across many calls."""

    __slots__ = ("prompt_tokens", "completion_tokens", "calls", "_lock")

    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.calls = 0
        self._lock = threading.Lock()

    def record(self, prompt_tokens: int, completion_tokens: int) -> None:
        with self._lock:
            self.prompt_tokens += prompt_tokens
            self.completion_tokens += completion_tokens
            self.calls += 1

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def merged(self, other: "TokenUsage") -> "TokenUsage":
        """Return a new TokenUsage that is the sum of self and other."""
        out = TokenUsage()
        out.prompt_tokens = self.prompt_tokens + other.prompt_tokens
        out.completion_tokens = self.completion_tokens + other.completion_tokens
        out.calls = self.calls + other.calls
        return out
