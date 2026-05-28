"""User-facing PDF styling knobs.

A :class:`PdfStyle` instance carries every visual choice that `build_pdf`
and `md_to_pdf` accept. Defaults reproduce the original look so calling
either function without a style behaves exactly as before.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Literal


PageSize = Literal["letter", "a4", "legal", "a3", "a5"]
FontFamily = Literal["helvetica", "times", "courier"]
Alignment = Literal["justify", "left"]


@dataclass
class PdfStyle:
    # Institutional assignment spec (do not loosen without explicit user request):
    #   A4 / Portrait / 0.5in margins all sides / Times New Roman 12pt / Justified
    #   Hard cap: 12 pages per submission.

    # --- page ---------------------------------------------------------------
    page_size: PageSize = "a4"
    margin_inches: float = 0.5

    # --- typography ---------------------------------------------------------
    font_family: FontFamily = "times"
    body_size: float = 12.0            # answer body text size (pt) — Times New Roman 12
    line_spacing: float = 1.43         # leading multiplier (leading = body_size * line_spacing)

    # --- title & headings ---------------------------------------------------
    title_size: float = 24.0
    question_size: float = 13.5
    h3_size: float = 11.5
    h4_size: float = 10.5

    # --- colors (hex strings, "#RRGGBB") ------------------------------------
    text_color: str = "#000000"
    separator_color: str = "#e2e8f0"

    # --- layout choices -----------------------------------------------------
    align: Alignment = "justify"       # alignment for answer prose
    show_separator: bool = True        # horizontal rule between questions

    # ------------------------------------------------------------------------

    @classmethod
    def field_names(cls) -> list[str]:
        return [f.name for f in fields(cls)]
