"""Markdown rendering for the qa pipeline.

Mirrors :func:`qa.pdf.build_pdf` but writes a `.md` file. The PDF builder
and its reportlab dependency are kept intact — this is an alternate sink.

Institutional assignment spec (the generated .md must satisfy these once
converted to PDF):
    - A4 / Portrait / 0.5in margins on all sides.
    - Times New Roman, 12pt body, justified alignment.
    - Hard cap: 12 pages total in the rendered PDF.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .config import DEFAULT_TITLE
from .types import QAPair


# Institutional PDF spec, surfaced here so the .md author and reviewer can see
# the constraints the downstream PDF render is held to.
PDF_SPEC = {
    "page_size": "A4",
    "orientation": "Portrait",
    "margin": "0.5 inch (all sides)",
    "font_family": "Times New Roman",
    "font_size": "12pt",
    "alignment": "Justified",
    "max_pages": 12,
}


def _timestamped(output_path: str) -> str:
    """Inject a timestamp before the file extension so every run writes a new
    file. `answers.md` → `answers-2026-05-23_141022.md`."""
    p = Path(output_path)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    suffix = p.suffix or ".md"
    return str(p.with_name(f"{p.stem}-{stamp}{suffix}"))


def build_md(
    output_path: str,
    qa_pairs: list[QAPair],
    *,
    title: str = DEFAULT_TITLE,
) -> str:
    """Render Q&A pairs to a Markdown file. Returns the actual path written.

    Layout: `# <title>` followed by numbered `## N. <question>` sections with
    the answer body underneath, separated by `---` horizontal rules. PDF
    formatting spec (A4, 0.5in margins, Times New Roman 12pt, justified,
    12-page cap) is logged for visibility.
    """
    # Local import to avoid a circular import: cli.__init__ pulls in qa.
    from cli.log import kv, warn

    output_path = _timestamped(output_path)

    for k, v in PDF_SPEC.items():
        kv(k, v)

    parts: list[str] = [f"# {title}", ""]
    for idx, (spec, answer) in enumerate(qa_pairs, start=1):
        parts.append(f"## {idx}. {spec.question}")
        parts.append("")
        parts.append(answer.rstrip())
        parts.append("")
        if idx != len(qa_pairs):
            parts.append("---")
            parts.append("")

    rendered = "\n".join(parts)
    Path(output_path).write_text(rendered, encoding="utf-8")

    word_count = len(rendered.split())
    kv("questions", len(qa_pairs))
    kv("words", word_count)
    # Rough page estimate at Times New Roman 12pt / 0.5in margins / A4:
    # ~600 words per page is a conservative practical figure at this margin.
    est_pages = max(1, round(word_count / 600))
    kv("est_pages", f"{est_pages} (cap {PDF_SPEC['max_pages']})")
    if est_pages > PDF_SPEC["max_pages"]:
        warn(
            f"estimated {est_pages} pages exceeds the {PDF_SPEC['max_pages']}-page cap — "
            "trim content before submission"
        )

    return output_path
