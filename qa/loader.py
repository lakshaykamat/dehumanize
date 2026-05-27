"""Read and validate the questions JSON file."""

from __future__ import annotations

import json

from .types import QuestionSpec


def _parse_words(value, item_idx: int, path: str) -> tuple[int, int]:
    """Parse the `words` field into (min_words, max_words).

    Accepts:
        "400-500"   range string
        400         single int (treated as exact: min == max)
    """
    if isinstance(value, str):
        s = value.strip()
        if "-" not in s:
            raise ValueError(
                f"{path}: item {item_idx} 'words' must be a range like '400-500' or an int.")
        lo_s, hi_s = s.split("-", 1)
        try:
            lo, hi = int(lo_s.strip()), int(hi_s.strip())
        except ValueError:
            raise ValueError(f"{path}: item {item_idx} 'words' has non-integer bounds: {value!r}.")
        if lo <= 0 or hi <= 0 or hi < lo:
            raise ValueError(f"{path}: item {item_idx} 'words' invalid range: {value!r}.")
        return lo, hi
    if isinstance(value, int) and not isinstance(value, bool):
        if value <= 0:
            raise ValueError(f"{path}: item {item_idx} 'words' must be positive.")
        return value, value
    raise ValueError(
        f"{path}: item {item_idx} 'words' must be a range string like '400-500' or a positive int.")


def read_questions(path: str) -> list[QuestionSpec]:
    """Read questions from a JSON file.

    Required shape — a list of objects with both fields:
        [
          {"question": "What is X?", "words": "400-500"},
          {"question": "Explain Y.", "words": 450}
        ]

    `words` accepts either a range string ("400-500") or a single int.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"{path}: top-level JSON must be a list of question objects.")

    specs: list[QuestionSpec] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: item {i} must be an object with 'question' and 'words'.")
        question = item.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"{path}: item {i} is missing a non-empty 'question' string.")
        if "words" not in item:
            raise ValueError(f"{path}: item {i} is missing 'words' (required).")
        lo, hi = _parse_words(item["words"], i, path)
        specs.append(QuestionSpec(question.strip(), lo, hi))

    if not specs:
        raise ValueError(f"No questions found in {path}")
    return specs


def validate_input(input_path: str) -> list[QuestionSpec]:
    """Parse and validate the input JSON. Raises ValueError on any problem.
    Run this BEFORE any OpenAI calls so bad input fails fast and free.
    """
    return read_questions(input_path)
