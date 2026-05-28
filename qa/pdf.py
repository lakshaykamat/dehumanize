"""PDF rendering for the qa pipeline (reportlab).

The visual look is fully driven by :class:`qa.pdf_style.PdfStyle`. Calling
:func:`build_pdf` with no style uses the dataclass defaults (which reproduce
the original look).
"""

from __future__ import annotations

import re
from datetime import datetime
from html import escape, unescape
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A3, A4, A5, LEGAL, LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFError, TTFont
from reportlab.platypus import HRFlowable, Paragraph, Preformatted, SimpleDocTemplate, Spacer, XPreformatted

from .config import DEFAULT_TITLE
from .pdf_highlight import highlight_code, highlight_inline
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
_FENCE_RE = re.compile(r"^\s*```([\w+-]*)\s*$")


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

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CODE_FONT_SEARCH_DIRS = (
    _REPO_ROOT / "fonts",
    Path.home() / "Library/Fonts",
    Path("/Library/Fonts"),
    Path("/Library/Fonts/Microsoft"),
    Path("/Applications/Microsoft Word.app/Contents/Resources/DFonts"),
    Path("/System/Library/Fonts"),
)
_REGISTERED_CODE_FONTS: dict[str, str] = {"Courier": "Courier"}


def _resolve_code_font(requested: str) -> str:
    """Return the font name to use for code. Registers a TTF on first request;
    on failure falls back to Courier so rendering never breaks.
    """
    if requested in _REGISTERED_CODE_FONTS:
        return _REGISTERED_CODE_FONTS[requested]
    candidates = (f"{requested}.ttf", f"{requested.lower()}.ttf", f"{requested}.otf")
    for d in _CODE_FONT_SEARCH_DIRS:
        for name in candidates:
            ttf = d / name
            if ttf.is_file():
                try:
                    pdfmetrics.registerFont(TTFont(requested, str(ttf)))
                    _REGISTERED_CODE_FONTS[requested] = requested
                    return requested
                except TTFError:
                    pass
    import warnings
    warnings.warn(
        f"Code font '{requested}' not found in {[str(d) for d in _CODE_FONT_SEARCH_DIRS]}. "
        f"Drop the TTF in ./fonts/ to enable it. Falling back to Courier.",
        stacklevel=2,
    )
    _REGISTERED_CODE_FONTS[requested] = "Courier"
    return "Courier"


def _inline_markup(text: str, style: PdfStyle | None = None) -> str:
    """Escape `text` for reportlab. Strip any bold/italic markdown markers
    (keep inner text as plain prose). Convert `code` to a monospace span
    with a soft background tint so it visually reads as code."""
    style = style or PdfStyle()
    out = escape(text)
    out = _BOLD_RE.sub(lambda m: m.group(1) or m.group(2), out)
    out = _ITALIC_RE.sub(lambda m: m.group(1) or m.group(2), out)
    bg = style.inline_code_bg
    fg = style.inline_code_color
    sz = style.inline_code_size
    face = _resolve_code_font(style.code_font_family)

    def _render_inline(m: re.Match) -> str:
        # `out` is already HTML-escaped at this point; unescape so the
        # inline highlighter sees raw source and its own escaping doesn't double up.
        snippet = unescape(m.group(1))
        try:
            inner = highlight_inline(
                snippet,
                default_color=fg,
                function_color=style.inline_code_function_color,
            )
        except Exception:
            inner = escape(snippet)
        return (
            f'<font face="{face}" size="{sz}" color="{fg}" backColor="{bg}">'
            f'{inner}</font>'
        )

    out = _CODE_RE.sub(_render_inline, out)
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
            leftIndent=22, bulletIndent=6, spaceAfter=6,
        ),
        "code_block": ParagraphStyle(
            "CodeBlock", parent=base["Code"],
            fontName=_resolve_code_font(style.code_font_family),
            fontSize=style.code_block_size,
            leading=style.code_block_size * 1.35,
            textColor=HexColor(style.code_block_color),
            backColor=HexColor(style.code_block_bg),
            borderColor=HexColor(style.code_block_bg),
            borderPadding=(8, 10, 8, 10),
            borderWidth=0,
            leftIndent=0, rightIndent=0,
            spaceBefore=6, spaceAfter=8,
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


def _flush_prose(buf: list[str], styles: dict, flowables: list, style: PdfStyle) -> None:
    if not buf:
        return
    text = " ".join(line.strip() for line in buf).strip()
    if text:
        flowables.append(Paragraph(_inline_markup(text, style), styles["answer"]))
        flowables.append(Spacer(1, 4))
    buf.clear()


def _flush_list(buf: list[tuple[str, str]], styles: dict, flowables: list, style: PdfStyle) -> None:
    if not buf:
        return
    for marker, body in buf:
        flowables.append(Paragraph(_inline_markup(body, style), styles["bullet"], bulletText=_bullet_for(marker)))
    flowables.append(Spacer(1, 6))
    buf.clear()


def _flush_code(buf: list[str], language: str, styles: dict, flowables: list, style: PdfStyle) -> None:
    """Render a captured fenced code block, syntax-highlighted via Pygments.
    The language hint comes from the opening fence (```python, ```sql, …);
    when missing or unknown, Pygments guesses; on total failure it falls back
    to a plain monochrome block."""
    if not buf:
        return
    # Drop trailing blank lines so the dark box doesn't have an empty bottom row.
    while buf and not buf[-1].strip():
        buf.pop()
    if not buf:
        return
    source = "\n".join(buf)
    try:
        markup = highlight_code(source, language, default_color=style.code_block_color)
        flowables.append(XPreformatted(markup, styles["code_block"]))
    except Exception:
        # Highlighting is a nice-to-have — never let it break the document.
        flowables.append(Preformatted(source, styles["code_block"]))
    flowables.append(Spacer(1, 4))
    buf.clear()


def _paragraphize(answer: str, styles: dict, style: PdfStyle) -> list:
    """Render an answer as a sequence of Paragraph/list/code flowables.
    Detects list items by their leading marker and renders them as proper
    bullets (so '-' / '1)' / '(a)' don't show up as literal text). Fenced
    ``` blocks ``` are rendered as a dark code block.
    """
    flowables: list = []
    prose_buf: list[str] = []
    list_buf: list[tuple[str, str]] = []
    code_buf: list[str] = []
    code_lang: str = ""
    in_code = False

    for raw_line in answer.splitlines():
        line = raw_line.rstrip()

        fence = _FENCE_RE.match(line)
        if fence:
            if in_code:
                _flush_code(code_buf, code_lang, styles, flowables, style)
                code_lang = ""
                in_code = False
            else:
                _flush_list(list_buf, styles, flowables, style)
                _flush_prose(prose_buf, styles, flowables, style)
                code_lang = fence.group(1) or ""
                in_code = True
            continue

        if in_code:
            code_buf.append(raw_line)
            continue

        if not line.strip():
            _flush_list(list_buf, styles, flowables, style)
            _flush_prose(prose_buf, styles, flowables, style)
            continue
        h = _HEADING_RE.match(line)
        if h:
            _flush_list(list_buf, styles, flowables, style)
            _flush_prose(prose_buf, styles, flowables, style)
            level = len(h.group(1))
            style_key = "h3" if level == 3 else "h4"
            flowables.append(Paragraph(_inline_markup(h.group(2), style), styles[style_key]))
            continue
        m = _LIST_LINE.match(line)
        if m:
            _flush_prose(prose_buf, styles, flowables, style)
            list_buf.append((m.group("marker"), m.group("body").strip()))
        else:
            _flush_list(list_buf, styles, flowables, style)
            prose_buf.append(line)

    # Unterminated fence: still render what we captured so content isn't lost.
    if in_code:
        _flush_code(code_buf, code_lang, styles, flowables, style)
    _flush_list(list_buf, styles, flowables, style)
    _flush_prose(prose_buf, styles, flowables, style)
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
    page_size = _PAGE_SIZES[style.page_size]
    doc = SimpleDocTemplate(
        output_path, pagesize=page_size,
        leftMargin=margin, rightMargin=margin,
        topMargin=margin, bottomMargin=margin,
        title=title,
    )
    styles = _build_styles(style)
    story = [Paragraph(escape(title), styles["title"])]

    separator_color = HexColor(style.separator_color)

    for idx, (spec, a) in enumerate(qa_pairs, start=1):
        story.append(Paragraph(f"{idx}. {_inline_markup(spec.question, style)}", styles["question"]))
        story.extend(_paragraphize(a, styles, style))
        if idx != len(qa_pairs) and style.show_separator:
            story.append(Spacer(1, 8))
            story.append(HRFlowable(width="40%", thickness=0.4, color=separator_color, spaceAfter=10))
        elif idx != len(qa_pairs):
            story.append(Spacer(1, 12))

    doc.build(story)
    return output_path
