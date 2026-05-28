"""Q&A → PDF pipeline.

Public API surface — re-exports from the sub-modules so callers can simply
`from qa import ...`.

Modules:
    config       constants and defaults
    types        QuestionSpec, ProgressEvent, MissingAPIKeyError
    loader       JSON input parsing and validation
    prompts      merged writer+formatter system prompt
    generator    OpenAI client + per-question answer generation (retry/inflation)
    pdf          reportlab rendering
    pipeline     high-level orchestration
"""

from .config import (
    DEFAULT_CONCURRENCY,
    DEFAULT_HUMANIZE_DENSITY,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TITLE,
    INFLATION_GUESS,
    MAX_RETRIES,
)
from .generator import ask_openai, generate_answers, make_client
from .loader import read_questions, validate_input
from .md import (
    apply_substitutions,
    build_md,
    find_placeholders,
    load_template_text,
    suggested_default,
)
from .md_to_pdf import md_to_pdf
from .pdf import build_pdf
from .pdf_style import PdfStyle
from .pipeline import questions_to_pdf
from .prompts import SYSTEM_PROMPT
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
    "DEFAULT_TEMPERATURE",
    "DEFAULT_TITLE",
    "INFLATION_GUESS",
    "MAX_RETRIES",
    # types
    "MissingAPIKeyError",
    "PdfStyle",
    "ProgressEvent",
    "ProgressFn",
    "QAPair",
    "QuestionSpec",
    "TokenUsage",
    # prompts
    "SYSTEM_PROMPT",
    # functions
    "apply_substitutions",
    "ask_openai",
    "build_md",
    "build_pdf",
    "find_placeholders",
    "load_template_text",
    "md_to_pdf",
    "suggested_default",
    "generate_answers",
    "make_client",
    "questions_to_pdf",
    "read_questions",
    "validate_input",
]
