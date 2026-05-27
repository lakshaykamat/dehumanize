"""argparse glue and the top-level :func:`main` dispatcher."""

from __future__ import annotations

import argparse
import sys

from . import wizard
from .commands import humanize_cmd, md_to_pdf_cmd, qa_md_cmd
from .env import load_dotenv
from .log import RESET, YELLOW, log


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dehumanize",
        description=(
            "Run with no arguments for the interactive wizard, "
            "or pass a subcommand to script it."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=False)
    humanize_cmd.add_parser(sub)
    qa_md_cmd.add_parser(sub)
    md_to_pdf_cmd.add_parser(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        try:
            return wizard.run()
        except KeyboardInterrupt:
            log(f"\n{YELLOW}cancelled.{RESET}")
            return 130

    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        try:
            return wizard.run()
        except KeyboardInterrupt:
            log(f"\n{YELLOW}cancelled.{RESET}")
            return 130
    return args.func(args)
