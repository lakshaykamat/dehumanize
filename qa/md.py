"""Markdown rendering for the qa pipeline.

Mirrors :func:`qa.pdf.build_pdf` but writes a `.md` file. The PDF builder
and its reportlab dependency are kept intact — this is an alternate sink.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .config import DEFAULT_TITLE
from .types import QAPair


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
    """Render Q&A pairs to a Markdown file. Returns the actual path written."""
    output_path = _timestamped(output_path)

    parts: list[str] = [f"# {title}", ""]
    for idx, (spec, answer) in enumerate(qa_pairs, start=1):
        parts.append(f"## {idx}. {spec.question}")
        parts.append("")
        parts.append(answer.rstrip())
        parts.append("")
        if idx != len(qa_pairs):
            parts.append("---")
            parts.append("")

    Path(output_path).write_text("\n".join(parts), encoding="utf-8")
    return output_path
