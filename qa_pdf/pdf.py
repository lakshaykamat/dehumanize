"""PDF rendering for the qa_pdf pipeline (reportlab)."""

from __future__ import annotations

import re
from datetime import datetime
from html import escape
from pathlib import Path

from reportlab.lib.colors import HexColor, black
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from .config import DEFAULT_TITLE
from .types import QAPair


_BOLD_RE = re.compile(r"\*\*(\S(?:.*?\S)?)\*\*|__(\S(?:.*?\S)?)__")
_ITALIC_RE = re.compile(
    r"(?:(?<=^)|(?<=[\s(\[{>]))"
    r"(?:\*(?!\*)(\S(?:[^*\n]*?\S)?)\*(?!\*)"
    r"|_(?!_)(\S(?:[^_\n]*?\S)?)_(?!_))"
    r"(?=$|[\s)\]}.,;:!?<])"
)
_CODE_RE = re.compile(r"`([^`\n]+?)`")


def _inline_markup(text: str) -> str:
    """Escape `text` for reportlab. Strip any bold/italic markdown markers
    (keep inner text as plain prose). Convert `code` to a monospace span."""
    out = escape(text)
    out = _BOLD_RE.sub(lambda m: m.group(1) or m.group(2), out)
    out = _ITALIC_RE.sub(lambda m: m.group(1) or m.group(2), out)
    out = _CODE_RE.sub(lambda m: f'<font face="Courier">{m.group(1)}</font>', out)
    return out


def _build_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "DocTitle", parent=base["Title"],
            fontName="Helvetica-Bold", fontSize=24, leading=28,
            textColor=black, alignment=TA_LEFT, spaceAfter=18,
        ),
        "question": ParagraphStyle(
            "Question", parent=base["Heading2"],
            fontName="Helvetica-Bold", fontSize=13.5, leading=18,
            textColor=black, spaceBefore=10, spaceAfter=6, keepWithNext=True,
        ),
        "answer": ParagraphStyle(
            "Answer", parent=base["BodyText"],
            fontName="Helvetica", fontSize=10.5, leading=15,
            textColor=black, alignment=TA_JUSTIFY, spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "Bullet", parent=base["BodyText"],
            fontName="Helvetica", fontSize=10.5, leading=15,
            textColor=black, alignment=TA_LEFT,
            leftIndent=22, bulletIndent=6, spaceAfter=2,
        ),
    }


# Detects a line that opens a list item. Captures the marker and the body.
_LIST_LINE = re.compile(
    r"^\s*"
    r"(?P<marker>"
    r"[-*•·]"                       # - * • ·
    r"|\(?\d+[.)]"                  # 1. 1) (1)
    r"|\(?[A-Za-z][.)]"             # a. a) (a)
    r")"
    r"\s+(?P<body>.+)$"
)


def _bullet_for(marker: str) -> str:
    """Return the visual bullet to render for a captured marker."""
    m = marker.strip().lstrip("(")
    if m and m[0] in "-*•·":
        return "•"
    if m.endswith(")"):
        m = m[:-1] + "."
    return m


def _flush_prose(buf: list[str], styles: dict, flowables: list) -> None:
    if not buf:
        return
    text = " ".join(line.strip() for line in buf).strip()
    if text:
        flowables.append(Paragraph(_inline_markup(text), styles["answer"]))
        flowables.append(Spacer(1, 4))
    buf.clear()


def _flush_list(buf: list[tuple[str, str]], styles: dict, flowables: list) -> None:
    if not buf:
        return
    for marker, body in buf:
        flowables.append(Paragraph(_inline_markup(body), styles["bullet"], bulletText=_bullet_for(marker)))
    flowables.append(Spacer(1, 6))
    buf.clear()


def _paragraphize(answer: str, styles: dict) -> list:
    """Render an answer as a sequence of Paragraph/list flowables.
    Detects list items by their leading marker and renders them as proper
    bullets (so '-' / '1)' / '(a)' don't show up as literal text).
    """
    flowables: list = []
    prose_buf: list[str] = []
    list_buf: list[tuple[str, str]] = []

    for raw_line in answer.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            _flush_list(list_buf, styles, flowables)
            _flush_prose(prose_buf, styles, flowables)
            continue
        m = _LIST_LINE.match(line)
        if m:
            _flush_prose(prose_buf, styles, flowables)
            list_buf.append((m.group("marker"), m.group("body").strip()))
        else:
            _flush_list(list_buf, styles, flowables)
            prose_buf.append(line)

    _flush_list(list_buf, styles, flowables)
    _flush_prose(prose_buf, styles, flowables)
    return flowables


def _timestamped(output_path: str) -> str:
    """Inject a timestamp before the file extension so every run writes a new
    file and never overwrites an existing one. `answers.pdf` →
    `answers-2026-05-23_141022.pdf`. The parent directory is preserved.
    """
    p = Path(output_path)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    suffix = p.suffix or ".pdf"
    return str(p.with_name(f"{p.stem}-{stamp}{suffix}"))


def build_pdf(
    output_path: str,
    qa_pairs: list[QAPair],
    *,
    title: str = DEFAULT_TITLE,
) -> str:
    """Render the Q&A pairs to a PDF. A timestamp is always appended to the
    filename so existing files are never overwritten. Returns the actual path
    written.
    """
    output_path = _timestamped(output_path)
    doc = SimpleDocTemplate(
        output_path, pagesize=LETTER,
        leftMargin=0.85 * inch, rightMargin=0.85 * inch,
        topMargin=0.85 * inch, bottomMargin=0.85 * inch,
        title=title,
    )
    styles = _build_styles()
    story = [Paragraph(escape(title), styles["title"])]

    for idx, (spec, a) in enumerate(qa_pairs, start=1):
        story.append(Paragraph(f"{idx}. {_inline_markup(spec.question)}", styles["question"]))
        story.extend(_paragraphize(a, styles))
        if idx != len(qa_pairs):
            story.append(Spacer(1, 8))
            story.append(HRFlowable(width="40%", thickness=0.4, color=HexColor("#e2e8f0"), spaceAfter=10))

    doc.build(story)
    return output_path
