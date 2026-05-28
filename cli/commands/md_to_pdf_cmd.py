"""`md-to-pdf` subcommand — convert an existing Markdown file to PDF.

Every visual knob in :class:`qa.PdfStyle` is exposed as a CLI flag.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import fields
from pathlib import Path

from qa import PdfStyle, md_to_pdf

from ..log import DIM, GREEN, RESET, err, fmt_duration, kv, log, ok, section, step


PAGE_SIZES = ["letter", "a4", "legal", "a3", "a5"]
FONT_FAMILIES = ["helvetica", "times", "courier"]
ALIGNMENTS = ["justify", "left"]

_HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


def _normalize_hex(value: str, field_name: str) -> str:
    v = value.strip()
    if not _HEX_RE.match(v):
        raise ValueError(f"{field_name} must be a 6-digit hex color (e.g. #1a2b3c), got {value!r}")
    return v if v.startswith("#") else f"#{v}"


def add_parser(sub) -> None:
    defaults = PdfStyle()
    p = sub.add_parser(
        "md-to-pdf",
        help="Render a Markdown file as PDF (no OpenAI calls).",
        description="Render a Markdown file as PDF. Supports the standard "
                    "institutional layout out of the box.",
    )
    p.add_argument("input", help="Input Markdown file (e.g. answers.md).")
    p.add_argument("-o", "--output", required=True,
                   help="Output PDF path (e.g. answers.pdf). A timestamp is appended.")
    p.add_argument("-t", "--title", default=None,
                   help="Override the document title (defaults to the H1 in the markdown).")

    style = p.add_argument_group("PDF style", "Visual knobs — defaults reproduce the standard look.")
    style.add_argument("--page-size", choices=PAGE_SIZES, default=defaults.page_size,
                       help=f"Page size (default: {defaults.page_size}).")
    style.add_argument("--margin", type=float, default=defaults.margin_inches,
                       metavar="INCHES",
                       help=f"Page margin in inches, all sides (default: {defaults.margin_inches}).")
    style.add_argument("--font", choices=FONT_FAMILIES, default=defaults.font_family,
                       dest="font_family",
                       help=f"Font family (default: {defaults.font_family}).")
    style.add_argument("--body-size", type=float, default=defaults.body_size, metavar="PT",
                       help=f"Body text size in points (default: {defaults.body_size}).")
    style.add_argument("--line-spacing", type=float, default=defaults.line_spacing, metavar="MULT",
                       help=f"Line-height multiplier (default: {defaults.line_spacing}).")
    style.add_argument("--title-size", type=float, default=defaults.title_size, metavar="PT",
                       help=f"Title size in points (default: {defaults.title_size}).")
    style.add_argument("--question-size", type=float, default=defaults.question_size, metavar="PT",
                       help=f"Question heading size in points (default: {defaults.question_size}).")
    style.add_argument("--h3-size", type=float, default=defaults.h3_size, metavar="PT",
                       help=f"H3 subheading size (default: {defaults.h3_size}).")
    style.add_argument("--h4-size", type=float, default=defaults.h4_size, metavar="PT",
                       help=f"H4 subheading size (default: {defaults.h4_size}).")
    style.add_argument("--text-color", default=defaults.text_color, metavar="HEX",
                       help=f"Hex color for all text (default: {defaults.text_color}).")
    style.add_argument("--separator-color", default=defaults.separator_color, metavar="HEX",
                       help=f"Hex color for the line between questions (default: {defaults.separator_color}).")
    style.add_argument("--align", choices=ALIGNMENTS, default=defaults.align,
                       help=f"Answer paragraph alignment (default: {defaults.align}).")
    style.add_argument("--no-separator", dest="show_separator", action="store_false",
                       help="Hide the horizontal rule between questions.")
    p.set_defaults(func=run, show_separator=defaults.show_separator)


def _style_from_args(args) -> PdfStyle:
    return PdfStyle(
        page_size=args.page_size,
        margin_inches=args.margin,
        font_family=args.font_family,
        body_size=args.body_size,
        line_spacing=args.line_spacing,
        title_size=args.title_size,
        question_size=args.question_size,
        h3_size=args.h3_size,
        h4_size=args.h4_size,
        text_color=_normalize_hex(args.text_color, "--text-color"),
        separator_color=_normalize_hex(args.separator_color, "--separator-color"),
        align=args.align,
        show_separator=args.show_separator,
    )


def _kv_style(style: PdfStyle) -> None:
    names = [f.name.replace("_", "-") for f in fields(style)]
    width = max(len(n) for n in names) + 2
    for f, name in zip(fields(style), names):
        log(f"  {DIM}{name:<{width}}{RESET}{getattr(style, f.name)}")


def run(args) -> int:
    started = time.perf_counter()
    section("md-to-pdf")
    kv("input", args.input)
    kv("output", args.output)
    kv("title", args.title or "(from H1 in markdown)")

    try:
        style = _style_from_args(args)
    except ValueError as e:
        err(str(e))
        return 1

    section("style")
    _kv_style(style)

    step(1, 2, "reading markdown")
    if not Path(args.input).is_file():
        err(f"input file not found: {args.input}")
        return 1
    size = os.path.getsize(args.input)
    ok(f"{size} bytes")

    step(2, 2, "rendering PDF")
    pdf_start = time.perf_counter()
    try:
        written_path = md_to_pdf(args.input, args.output, title=args.title, style=style)
    except ValueError as e:
        err(str(e))
        return 1
    out_size = os.path.getsize(written_path) if Path(written_path).is_file() else 0
    ok(f"{written_path}  {out_size} bytes  in {fmt_duration(time.perf_counter() - pdf_start)}")

    log(f"\n{GREEN}done{RESET} in {fmt_duration(time.perf_counter() - started)}")
    return 0
