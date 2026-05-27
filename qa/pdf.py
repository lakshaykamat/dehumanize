"""PDF rendering for the qa pipeline (reportlab).

The visual look is fully driven by :class:`qa.pdf_style.PdfStyle`. Calling
:func:`build_pdf` with no style uses the dataclass defaults (which reproduce
the original look).
"""

from __future__ import annotations

import re
from datetime import datetime
from html import escape
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A3, A4, A5, LEGAL, LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from .config import DEFAULT_TITLE
from .pdf_style import PdfStyle
from .types import QAPair


_BOLD_RE = re.compile(r"\*\*(\S(?:.*?\S)?)\*\*|__(\S(?:.*?\S)?)__")
_ITALIC_RE = re.compile(
    r"(?:(?<=^)|(?<=[\s(\[{>]))"
    r"(?:\*(?!\*)(\S(?:[^*\n]*?\S)?)\*(?!\*)"
    r"|_(?!_)(\S(?:[^_\n]*?\S)?)_(?!_))"
    r"(?=$|[\s)\]}.,;:!?<])"
)
_CODE_RE = re.compile(r"`([^`\n]+?)`")
_HEADING_RE = re.compile(r"^\s*(#{3,4})\s+(.+?)\s*#*\s*$")


_PAGE_SIZES = {
    "letter": LETTER,
    "a4": A4,
    "legal": LEGAL,
    "a3": A3,
    "a5": A5,
}

_FONT_FAMILIES = {
    "helvetica": ("Helvetica", "Helvetica-Bold"),
    "times": ("Times-Roman", "Times-Bold"),
    "courier": ("Courier", "Courier-Bold"),
}

_ALIGN = {"justify": TA_JUSTIFY, "left": TA_LEFT}


def _inline_markup(text: str) -> str:
    """Escape `text` for reportlab. Strip any bold/italic markdown markers
    (keep inner text as plain prose). Convert `code` to a monospace span."""
    out = escape(text)
    out = _BOLD_RE.sub(lambda m: m.group(1) or m.group(2), out)
    out = _ITALIC_RE.sub(lambda m: m.group(1) or m.group(2), out)
    out = _CODE_RE.sub(lambda m: f'<font face="Courier">{m.group(1)}</font>', out)
    return out


def _build_styles(style: PdfStyle):
    base = getSampleStyleSheet()
    regular, bold = _FONT_FAMILIES[style.font_family]
    text = HexColor(style.text_color)
    body_leading = style.body_size * style.line_spacing
    answer_align = _ALIGN[style.align]
    return {
        "title": ParagraphStyle(
            "DocTitle", parent=base["Title"],
            fontName=bold, fontSize=style.title_size, leading=style.title_size * 1.17,
            textColor=text, alignment=TA_LEFT, spaceAfter=18,
        ),
        "question": ParagraphStyle(
            "Question", parent=base["Heading2"],
            fontName=bold, fontSize=style.question_size,
            leading=style.question_size * 1.33,
            textColor=text, spaceBefore=10, spaceAfter=6, keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "H3", parent=base["Heading3"],
            fontName=bold, fontSize=style.h3_size, leading=style.h3_size * 1.3,
            textColor=text, spaceBefore=8, spaceAfter=4, keepWithNext=True,
        ),
        "h4": ParagraphStyle(
            "H4", parent=base["Heading4"],
            fontName=bold, fontSize=style.h4_size, leading=style.h4_size * 1.33,
            textColor=text, spaceBefore=6, spaceAfter=3, keepWithNext=True,
        ),
        "answer": ParagraphStyle(
            "Answer", parent=base["BodyText"],
            fontName=regular, fontSize=style.body_size, leading=body_leading,
            textColor=text, alignment=answer_align, spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "Bullet", parent=base["BodyText"],
            fontName=regular, fontSize=style.body_size, leading=body_leading,
            textColor=text, alignment=TA_LEFT,
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
        h = _HEADING_RE.match(line)
        if h:
            _flush_list(list_buf, styles, flowables)
            _flush_prose(prose_buf, styles, flowables)
            level = len(h.group(1))
            style_key = "h3" if level == 3 else "h4"
            flowables.append(Paragraph(_inline_markup(h.group(2)), styles[style_key]))
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
    style: PdfStyle | None = None,
) -> str:
    """Render the Q&A pairs to a PDF. A timestamp is always appended to the
    filename so existing files are never overwritten. Returns the actual path
    written.

    `style` controls every visual choice. Pass `None` (default) for the
    standard look.
    """
    style = style or PdfStyle()
    output_path = _timestamped(output_path)
    margin = style.margin_inches * inch
    doc = SimpleDocTemplate(
        output_path, pagesize=_PAGE_SIZES[style.page_size],
        leftMargin=margin, rightMargin=margin,
        topMargin=margin, bottomMargin=margin,
        title=title,
    )
    styles = _build_styles(style)
    story = [Paragraph(escape(title), styles["title"])]

    separator_color = HexColor(style.separator_color)

    for idx, (spec, a) in enumerate(qa_pairs, start=1):
        story.append(Paragraph(f"{idx}. {_inline_markup(spec.question)}", styles["question"]))
        story.extend(_paragraphize(a, styles))
        if idx != len(qa_pairs) and style.show_separator:
            story.append(Spacer(1, 8))
            story.append(HRFlowable(width="40%", thickness=0.4, color=separator_color, spaceAfter=10))
        elif idx != len(qa_pairs):
            story.append(Spacer(1, 12))

    doc.build(story)
    return output_path
