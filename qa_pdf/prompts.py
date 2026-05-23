"""System and user prompt templates for the qa_pdf pipeline."""

from __future__ import annotations

from .types import QuestionSpec


SYSTEM_PROMPT = """\
You write study-reference answers for a PDF.

VOICE
- Very basic English: short, simple, common words; short sentences.
- Professional tone: calm, clear, respectful.
- No greetings, disclaimers, meta commentary, or restating the question.

STRUCTURE
- Mix paragraphs and lists. Open with one or two short paragraphs, then a list for enumerable parts, then a short closing paragraph if it helps.
- Never an answer that is only prose. Never an answer that is only a list.

LISTS
- Use bullets ("- item") for unordered things: features, advantages, categories, options.
- Use a numbered list ("1. item") when order matters: steps, ranks, sequences.
- An answer may contain both — one bullet list and one numbered list — separated by a blank line.
- One short phrase or sentence per item. No blank lines inside a list. No nesting.

INLINE FORMATTING
- Plain text only. Use `code` for a literal identifier, command, filename, or value when relevant.
- Never use bold or italic. Do not write **…**, __…__, *…*, or _…_ anywhere.

FORBIDDEN
Bold, italic, headings, blockquotes, tables, fenced code blocks, images, hyperlinks, nested lists, emoji.

Hit the word target the user gives you.\
"""


FORMAT_SYSTEM_PROMPT = """\
You are a strict text formatter. The input may contain hedging connector phrases (e.g. "In this context,", "Furthermore,") injected directly in front of a list marker like "2)" or "(b)", which breaks the list visually.

Clean up formatting only:
1. Put every list item on its own line, starting with its marker (-, *, 1., 1), (a), etc.).
2. If a connector phrase sits in front of a list marker on the same line, move it to the previous paragraph, or drop it if it dangles between two list items.
3. Preserve all wording exactly. Do not paraphrase, rewrite, add, remove, or shorten anything.
4. Strip any bold (**…**, __…__) or italic (*…*, _…_) markers, keeping the inner text as plain prose. Preserve existing `code` spans exactly. Do not add new inline markup, headings, blockquotes, tables, or code blocks.
5. No greetings, disclaimers, meta commentary, or restating the question. Output the cleaned text only.\
"""


def _prompt_window(target_raw: int) -> tuple[int, int]:
    """Tight window around the raw target we ask the model for."""
    return max(30, target_raw - 20), target_raw + 20


def initial_prompt(spec: QuestionSpec, target_raw: int) -> str:
    lo, hi = _prompt_window(target_raw)
    return (
        f"Question: {spec.question}\n\n"
        f"Length: {target_raw} words (range {lo}-{hi}; hard cap {hi})."
    )


def retry_prompt(
    spec: QuestionSpec,
    previous_raw: str,
    previous_raw_words: int,
    final_words: int,
    target_raw: int,
) -> str:
    lo, hi = _prompt_window(target_raw)
    direction = "longer" if final_words < spec.min_words else "shorter"
    return (
        f"Previous answer was {final_words} words; target is {spec.range_str}. "
        f"Rewrite {direction}, aiming for {target_raw} words "
        f"(range {lo}-{hi}; hard cap {hi}).\n\n"
        f"Question: {spec.question}\n\n"
        f"Previous answer:\n{previous_raw}"
    )
