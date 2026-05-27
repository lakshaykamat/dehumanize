"""OpenAI client and per-question answer generation with retry + inflation calibration."""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable

from openai import OpenAI

from .config import DEFAULT_CONCURRENCY, DEFAULT_MODEL, DEFAULT_TEMPERATURE, MAX_RETRIES
from .prompts import SYSTEM_PROMPT, initial_prompt, retry_prompt
from .types import (
    MissingAPIKeyError,
    ProgressEvent,
    ProgressFn,
    QAPair,
    QuestionSpec,
    TokenUsage,
)


def make_client(api_key: str | None = None) -> OpenAI:
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise MissingAPIKeyError("OPENAI_API_KEY is not set.")
    return OpenAI(api_key=key)


def _word_count(text: str) -> int:
    return len(text.split())


def _within_range(words: int, spec: QuestionSpec) -> bool:
    return spec.min_words <= words <= spec.max_words


def _distance_to_range(words: int, spec: QuestionSpec) -> int:
    if words < spec.min_words:
        return spec.min_words - words
    if words > spec.max_words:
        return words - spec.max_words
    return 0


def _call_model(
    client: OpenAI,
    model: str,
    user_content: str,
    temperature: float,
    usage: TokenUsage | None = None,
) -> str:
    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
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


def ask_openai(
    client: OpenAI,
    model: str,
    spec: QuestionSpec,
    temperature: float,
    *,
    max_retries: int = MAX_RETRIES,
    post_transform: Callable[[str], str] | None = None,
    emit: Callable[[str, int, int | None], None] | None = None,
    initial_inflation: float = 1.0,
    usage: TokenUsage | None = None,
) -> str:
    """Ask one question, aiming for `spec.min_words..spec.max_words` AFTER an
    optional `post_transform` (e.g. humanize).

    Strategy: always ask the model for the LOWER end of the range, divided by
    an inflation factor (so humanize fills the range). After each attempt the
    actual inflation = final_words / raw_words is measured and the target is
    recalibrated. The model never sees the humanize math — it just gets a
    plain "write X words" instruction.
    """
    transform = post_transform or (lambda s: s)
    has_transform = post_transform is not None
    _emit = emit or (lambda *a, **k: None)
    inflation = max(1.0, float(initial_inflation)) if has_transform else 1.0

    def target_raw() -> int:
        return max(50, round(spec.min_words / inflation))

    tgt = target_raw()
    _emit("attempt", 1, None)
    raw = _call_model(client, model, initial_prompt(spec, tgt), temperature, usage)
    raw_words = _word_count(raw)
    final = transform(raw)
    final_words = _word_count(final)
    if has_transform and raw_words > 0:
        inflation = final_words / raw_words

    if _within_range(final_words, spec):
        _emit("ok", 1, final_words)
        return final

    best = final
    best_distance = _distance_to_range(final_words, spec)

    for attempt in range(2, max_retries + 2):
        _emit("retry", attempt - 1, final_words)
        tgt = target_raw()
        _emit("attempt", attempt, None)
        raw = _call_model(
            client, model,
            retry_prompt(spec, raw, raw_words, final_words, tgt),
            temperature,
            usage,
        )
        raw_words = _word_count(raw)
        final = transform(raw)
        final_words = _word_count(final)
        if has_transform and raw_words > 0:
            inflation = 0.5 * inflation + 0.5 * (final_words / raw_words)

        if _within_range(final_words, spec):
            _emit("ok", attempt, final_words)
            return final
        dist = _distance_to_range(final_words, spec)
        if dist < best_distance:
            best, best_distance = final, dist

    _emit("give_up", max_retries + 1, final_words)
    return best


def generate_answers(
    specs: Iterable[QuestionSpec],
    *,
    client: OpenAI | None = None,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    progress: ProgressFn | None = None,
    max_retries: int = MAX_RETRIES,
    post_transform: Callable[[str], str] | None = None,
    initial_inflation: float = 1.0,
    concurrency: int = DEFAULT_CONCURRENCY,
    usage: TokenUsage | None = None,
) -> list[QAPair]:
    """Ask the model each question (one prompt per question) and collect
    (spec, answer) pairs. Retries individual questions if the answer is
    outside the requested word range. When `post_transform` is set (e.g. the
    humanize step), the word check happens AFTER the transform, so inflation
    from humanizing is accounted for in the retry loop.

    Questions are dispatched concurrently up to `concurrency` in-flight. Per-
    question progress events are buffered in the worker and flushed as one
    contiguous block under a lock, so output stays readable.

    On per-question failure, the error message is stored as the answer so the
    PDF still renders.
    """
    client = client or make_client()
    specs = list(specs)
    total = len(specs)
    if total == 0:
        return []

    answers: list[str] = [""] * total
    workers = max(1, min(concurrency, total))
    flush_lock = threading.Lock()

    def _work(i: int, spec: QuestionSpec) -> None:
        buf: list[ProgressEvent] = [ProgressEvent("start", i, total, spec)]
        def _emit(kind: str, attempt: int, words: int | None) -> None:
            buf.append(ProgressEvent(kind, i, total, spec, attempt=attempt, words=words))
        try:
            answer = ask_openai(
                client, model, spec, temperature,
                max_retries=max_retries,
                post_transform=post_transform,
                emit=_emit,
                initial_inflation=initial_inflation,
                usage=usage,
            )
        except Exception as e:
            answer = f"(Error generating answer: {e})"
            buf.append(ProgressEvent("give_up", i, total, spec, attempt=0, words=None))
        answers[i - 1] = answer
        if progress:
            with flush_lock:
                for ev in buf:
                    progress(ev)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_work, i, spec) for i, spec in enumerate(specs, start=1)]
        for f in futures:
            f.result()

    return list(zip(specs, answers))
