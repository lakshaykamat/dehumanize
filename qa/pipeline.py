"""High-level orchestration: validate → generate (writer + format + humanize) → render."""

from __future__ import annotations

from humanize import humanize_pipeline

from .config import (
    DEFAULT_CONCURRENCY,
    DEFAULT_HUMANIZE_DENSITY,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TITLE,
    INFLATION_GUESS,
)
from .generator import generate_answers, make_client
from .loader import validate_input
from .pdf import build_pdf
from .reformatter import reformat_answer
from .types import ProgressFn


def questions_to_pdf(
    input_path: str,
    output_path: str,
    *,
    model: str = DEFAULT_MODEL,
    title: str = DEFAULT_TITLE,
    temperature: float = DEFAULT_TEMPERATURE,
    progress: ProgressFn | None = None,
    humanize_density: str = DEFAULT_HUMANIZE_DENSITY,
    humanize_seed: int | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    reformat: bool = True,
) -> int:
    """End-to-end: validate JSON → ask OpenAI (writer → formatter → humanize)
    → write PDF. Returns the QA count.

    Per question: writer produces clean prose, formatter (LLM) restructures it
    into markdown, then the markdown-aware humanizer injects filler ONLY into
    prose and bullet bodies (headings, table rows, and bold labels stay clean).
    The composed transform runs inside the retry loop so the word-count check
    sees the final humanized text.
    """
    specs = validate_input(input_path)
    client = make_client()

    def transform(text: str) -> str:
        if reformat:
            try:
                text = reformat_answer(client, model, text)
            except Exception:
                pass  # keep unformatted text if the format pass fails
        return humanize_pipeline(text, density=humanize_density, seed=humanize_seed)

    initial_inflation = INFLATION_GUESS.get(humanize_density, 1.0)

    qa_pairs = generate_answers(
        specs,
        client=client,
        model=model,
        temperature=temperature,
        progress=progress,
        post_transform=transform,
        initial_inflation=initial_inflation,
        concurrency=concurrency,
    )
    build_pdf(output_path, qa_pairs, title=title)
    return len(qa_pairs)
