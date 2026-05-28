"""argparse glue and the top-level :func:`main` dispatcher."""

from __future__ import annotations

import argparse
import sys

from .commands import humanize_cmd, md_to_pdf_cmd, qa_md_cmd
from .env import load_dotenv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dehumanize",
        description="Humanize text, generate Q&A markdown, and render PDFs.",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>", required=True)
    humanize_cmd.add_parser(sub)
    qa_md_cmd.add_parser(sub)
    md_to_pdf_cmd.add_parser(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return args.func(args)
