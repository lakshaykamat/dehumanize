#!/usr/bin/env python3
"""Unified CLI entry point. All logic lives in the `cli` package.

Subcommands:
    humanize    Inject filler words into text to make it sound human.
    qa-md       Ask OpenAI a list of questions and render a clean Markdown file.
    md-to-pdf   Convert an existing Markdown file to PDF (no API calls).

Examples:
    python main.py humanize para.txt
    python main.py humanize para.txt -d high -s 42 -o out.txt
    cat para.txt | python main.py humanize

    python main.py qa-md questions.json -o answers.md
    python main.py qa-md questions.json -o answers.md -m gpt-4o-mini -t "Interview Prep"

    python main.py md-to-pdf answers.md -o answers.pdf
    python main.py md-to-pdf answers.md -o answers.pdf -t "Final Submission"
"""

from cli import main


if __name__ == "__main__":
    raise SystemExit(main())
