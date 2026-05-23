"""AI-driven formatting cleanup pass. Preserves wording, fixes list layout."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from openai import OpenAI

from .config import DEFAULT_CONCURRENCY
from .prompts import FORMAT_SYSTEM_PROMPT
from .types import QAPair, QuestionSpec, TokenUsage


def reformat_answer(
    client: OpenAI,
    model: str,
    text: str,
    usage: TokenUsage | None = None,
) -> str:
    """Send `text` through OpenAI for a structure-only cleanup pass.
    Wording is preserved; only list layout / misplaced connector phrases are fixed.
    """
    resp = client.chat.completions.create(
        model=model,
        temperature=0.0,
        messages=[
            {"role": "system", "content": FORMAT_SYSTEM_PROMPT},
            {"role": "user", "content": f"Clean up the formatting of this text:\n\n{text}"},
        ],
    )
    if usage is not None:
        u = getattr(resp, "usage", None)
        if u is not None:
            usage.record(
                getattr(u, "prompt_tokens", 0) or 0,
                getattr(u, "completion_tokens", 0) or 0,
            )
    return resp.choices[0].message.content.strip()


def reformat_pairs(
    qa_pairs: list[QAPair],
    *,
    client: OpenAI,
    model: str,
    progress: Callable[[int, int, QuestionSpec, int, int], None] | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    usage: TokenUsage | None = None,
) -> list[QAPair]:
    """Run each (spec, answer) through `reformat_answer` in parallel. Returns
    a new list with the original ordering.

    If the formatter call fails for a question, the original answer is kept.
    `progress(i, total, spec, words_before, words_after)` is called per
    question under a lock so prints stay readable across threads.
    """
    total = len(qa_pairs)
    if total == 0:
        return []

    cleaned_answers: list[str] = [""] * total
    workers = max(1, min(concurrency, total))
    progress_lock = threading.Lock()

    def _work(i: int, spec: QuestionSpec, answer: str) -> None:
        before = len(answer.split())
        try:
            cleaned = reformat_answer(client, model, answer, usage=usage)
        except Exception:
            cleaned = answer
        cleaned_answers[i - 1] = cleaned
        if progress:
            with progress_lock:
                progress(i, total, spec, before, len(cleaned.split()))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_work, i, spec, answer)
                   for i, (spec, answer) in enumerate(qa_pairs, start=1)]
        for f in futures:
            f.result()

    return [(spec, cleaned_answers[i]) for i, (spec, _) in enumerate(qa_pairs)]
