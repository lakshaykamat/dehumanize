"""Markdown rendering for the qa pipeline.

Mirrors :func:`qa.pdf.build_pdf` but writes a `.md` file. The PDF builder
and its reportlab dependency are kept intact — this is an alternate sink.

Institutional assignment spec (the generated .md must satisfy these once
converted to PDF):
    - Cover page from `sample/template.md` prepended verbatim.
    - A4 / Portrait / 0.5in margins on all sides.
    - Times New Roman, 12pt body, justified alignment.
    - Hard cap: 12 pages total in the rendered PDF.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .config import DEFAULT_TITLE
from .types import QAPair


# Cover-page placeholders look like `[Your Name]`, `[e.g. JAN-FEB 2026]`.
# Negative-lookahead for `(` skips markdown link syntax `[text](url)`.
_PLACEHOLDER_RE = re.compile(r"\[([^\]\n]+)\](?!\()")


def find_placeholders(text: str) -> list[str]:
    """Return unique `[...]` placeholders in writer order (brackets included)."""
    seen: list[str] = []
    seen_set: set[str] = set()
    for m in _PLACEHOLDER_RE.finditer(text):
        full = m.group(0)
        if full not in seen_set:
            seen.append(full)
            seen_set.add(full)
    return seen


def suggested_default(placeholder: str) -> str:
    """For `[e.g. X]` style placeholders, suggest `X` as the default value.
    Returns empty string when there is no example hint to lift."""
    inner = placeholder[1:-1].strip()
    low = inner.lower()
    if low.startswith("e.g."):
        return inner[4:].lstrip(" .:")
    if low.startswith("eg."):
        return inner[3:].lstrip(" .:")
    return ""


def apply_substitutions(text: str, substitutions: dict[str, str]) -> str:
    """Replace every placeholder key with its substitution value in `text`."""
    for key, val in substitutions.items():
        text = text.replace(key, val)
    return text


def load_template_text() -> str | None:
    """Return the raw cover-page template text, or None when the file is missing."""
    if not TEMPLATE_PATH.is_file():
        return None
    return TEMPLATE_PATH.read_text(encoding="utf-8").rstrip()


# Cover-page template prepended to every generated answer .md. Resolved
# relative to the repo root (parent of the `qa` package).
TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "sample" / "template.md"

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
    substitutions: dict[str, str] | None = None,
) -> str:
    """Render Q&A pairs to a Markdown file. Returns the actual path written.

    The cover-page template at `sample/template.md` is prepended verbatim
    before the answer body. `substitutions` (e.g. {"[Your Name]": "Lakshay"})
    is applied to the template BEFORE prepending — so the resulting .md is
    fully filled and the downstream md→pdf converter does no further mutation.
    PDF formatting spec (A4, 1in margins, Times New Roman 12pt, justified,
    12-page cap) is logged for visibility.
    """
    # Local import to avoid a circular import: cli.__init__ pulls in qa.
    from cli.log import info, kv, warn

    output_path = _timestamped(output_path)

    info(f"md spec: {PDF_SPEC}")
    for k, v in PDF_SPEC.items():
        kv(k, v)

    template_text = load_template_text()
    if template_text is None:
        warn(f"template not found at {TEMPLATE_PATH} — skipping cover page")
        template_text = ""
    elif substitutions:
        template_text = apply_substitutions(template_text, substitutions)
        info(f"applied {len(substitutions)} placeholder substitution(s) to cover page")

    parts: list[str] = []
    if template_text:
        parts.append(template_text)
        parts.append("")
        parts.append("---")
        parts.append("")
        info(f"cover page prepended from {TEMPLATE_PATH.name}")

    parts.extend([f"# {title}", ""])
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
