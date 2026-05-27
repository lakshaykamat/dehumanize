"""Command-line entry point.

Importing :func:`main` runs the top-level dispatcher. Individual subcommands
live in :mod:`cli.commands` and share helpers from :mod:`cli.log`,
:mod:`cli.env`, and :mod:`cli.prompts`.
"""

from .entry import main

__all__ = ["main"]
