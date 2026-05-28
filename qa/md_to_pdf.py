"""Convert a Markdown file (as produced by :func:`build_md`) back to PDF.

Re-uses :func:`qa.pdf.build_pdf` so styling stays identical between the
direct generation path and the conversion path.

Expected input shape (lenient — extra blank lines and trailing whitespace are
fine):

    # Title

    ## 1. Question text

    Answer prose, with optional bullets / numbered lists / ### sub-headings.

    ---

    ## 2. Next question

    ...
"""

from __future__ import annotations

import re
from pathlib import Path

from .config import DEFAULT_TITLE
from .pdf import build_pdf
from .pdf_style import PdfStyle
from .types import QAPair, QuestionSpec


_H1_RE = re.compile(r"^#\s+(.+?)\s*$")
_H2_RE = re.compile(r"^##\s+(?:\d+\.\s*)?(.+?)\s*$")
_HR_RE = re.compile(r"^\s*-{3,}\s*$")


def _parse_md(text: str, fallback_title: str) -> tuple[str, list[str], list[QAPair]]:
    """Return (title, cover_lines, qa_pairs) parsed from a markdown document.

    `cover_lines` is everything that appears AFTER the first H1 (the title)
    and BEFORE the first H2 (the first question). Typically this is the
    assignment cover-page table prepended by `build_md`.

    QuestionSpec word ranges are not preserved in the markdown form, so we fill
    them with zeros — they are not used by build_pdf for rendering.
    """
    title: str | None = None
    cover_lines: list[str] = []
    pairs: list[tuple[str, list[str]]] = []  # (question, body lines)
    current_question: str | None = None
    current_body: list[str] = []

    for raw in text.splitlines():
        line = raw.rstrip()

        if title is None:
            m = _H1_RE.match(line)
            if m:
                title = m.group(1).strip()
                continue

        m2 = _H2_RE.match(line)
        if m2:
            if current_question is not None:
                pairs.append((current_question, current_body))
            current_question = m2.group(1).strip()
            current_body = []
            continue

        if current_question is None:
            # Content between the title H1 and the first question — cover page.
            cover_lines.append(line)
            continue

        if _HR_RE.match(line):
            # Horizontal rule between questions — treat as a break, not body.
            continue

        current_body.append(line)

    if current_question is not None:
        pairs.append((current_question, current_body))

    qa_pairs: list[QAPair] = [
        (QuestionSpec(question=q, min_words=0, max_words=0), _trim_body(body))
        for q, body in pairs
    ]

    # Trim leading/trailing blanks from the cover block.
    while cover_lines and not cover_lines[0].strip():
        cover_lines.pop(0)
    while cover_lines and not cover_lines[-1].strip():
        cover_lines.pop()

    return (title or fallback_title), cover_lines, qa_pairs


def _trim_body(lines: list[str]) -> str:
    """Strip leading/trailing blank lines from a body block."""
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def md_to_pdf(
    input_path: str,
    output_path: str,
    *,
    title: str | None = None,
    style: PdfStyle | None = None,
) -> str:
    """Read a markdown file and render it as PDF. Returns the actual PDF path.

    Pure conversion — the input markdown must already contain everything that
    should appear in the PDF (including the cover page if any). No template
    prepending and no placeholder substitution happens here. The render style
    enforces the institutional spec: A4 / Portrait / 0.5in margins / Times New
    Roman 12pt / Justified / 12-page cap (see :class:`PdfStyle`).
    """
    text = Path(input_path).read_text(encoding="utf-8")
    parsed_title, cover_lines, qa_pairs = _parse_md(text, fallback_title=title or DEFAULT_TITLE)
    if not qa_pairs:
        raise ValueError(f"No questions (## headings) found in {input_path}.")
    final_title = title if title else parsed_title
    return build_pdf(
        output_path, qa_pairs, title=final_title, style=style, cover_lines=cover_lines,
    )
