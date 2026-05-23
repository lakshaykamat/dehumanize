"""Q&A → PDF pipeline.

Public API surface — re-exports from the sub-modules so callers can simply
`from qa_pdf import ...`.

Modules:
    config       constants and defaults
    types        QuestionSpec, ProgressEvent, MissingAPIKeyError
    loader       JSON input parsing and validation
    prompts      system + user prompt templates
    generator    OpenAI client + per-question answer generation (retry/inflation)
    reformatter  AI formatting cleanup pass
    pdf          reportlab rendering
    pipeline     high-level orchestration
"""

from .config import (
    DEFAULT_CONCURRENCY,
    DEFAULT_HUMANIZE_DENSITY,
    DEFAULT_MODEL,
    DEFAULT_REFORMAT,
    DEFAULT_TEMPERATURE,
    DEFAULT_TITLE,
    INFLATION_GUESS,
    MAX_RETRIES,
)
from .generator import ask_openai, generate_answers, make_client
from .loader import read_questions, validate_input
from .pdf import build_pdf
from .pipeline import humanize_pairs, questions_to_pdf
from .prompts import FORMAT_SYSTEM_PROMPT, SYSTEM_PROMPT
from .reformatter import reformat_answer, reformat_pairs
from .types import (
    MissingAPIKeyError,
    ProgressEvent,
    ProgressFn,
    QAPair,
    QuestionSpec,
    TokenUsage,
)

__all__ = [
    # config
    "DEFAULT_CONCURRENCY",
    "DEFAULT_HUMANIZE_DENSITY",
    "DEFAULT_MODEL",
    "DEFAULT_REFORMAT",
    "DEFAULT_TEMPERATURE",
    "DEFAULT_TITLE",
    "INFLATION_GUESS",
    "MAX_RETRIES",
    # types
    "MissingAPIKeyError",
    "ProgressEvent",
    "ProgressFn",
    "QAPair",
    "QuestionSpec",
    "TokenUsage",
    # prompts
    "FORMAT_SYSTEM_PROMPT",
    "SYSTEM_PROMPT",
    # functions
    "ask_openai",
    "build_pdf",
    "generate_answers",
    "humanize_pairs",
    "make_client",
    "questions_to_pdf",
    "read_questions",
    "reformat_answer",
    "reformat_pairs",
    "validate_input",
]
