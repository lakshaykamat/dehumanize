"""High-level orchestration: validate → generate → reformat → render."""

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
from .types import ProgressFn, QAPair


def humanize_pairs(
    qa_pairs: list[QAPair],
    *,
    density: str = DEFAULT_HUMANIZE_DENSITY,
    seed: int | None = None,
) -> list[QAPair]:
    """Run each answer through the humanize pipeline. Questions are untouched."""
    return [(spec, humanize_pipeline(answer, density=density, seed=seed))
            for spec, answer in qa_pairs]


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
) -> int:
    """End-to-end: validate JSON → ask OpenAI (with humanize-aware word retry)
    → write PDF. Returns the QA count.

    Humanize always runs INSIDE the retry loop so the word count check sees
    the post-humanize text. Inflation from filler words is therefore included
    in the target range.
    """
    specs = validate_input(input_path)
    client = make_client()

    def transform(text: str) -> str:
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
