"""Top-level interactive wizard — picks which subcommand to run."""

from __future__ import annotations

from .commands import humanize_cmd, md_to_pdf_cmd, qa_md_cmd
from .log import log, section
from .prompts import ask_menu


_HANDLERS = {
    "qa-md": qa_md_cmd.interactive,
    "humanize": humanize_cmd.interactive,
    "md-to-pdf": md_to_pdf_cmd.interactive,
}


def run() -> int:
    section("dehumanize")
    log("Welcome. This wizard will guide you step by step.\n")
    mode = ask_menu(
        "What do you want to do?",
        [
            ("qa-md", "generate a Q&A Markdown file from a questions JSON (uses OpenAI)"),
            ("humanize", "add filler words to a text file"),
            ("md-to-pdf", "convert an existing Markdown file to PDF"),
        ],
        default="qa-md",
    )
    return _HANDLERS[mode]()
