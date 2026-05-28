"""Command-line entry point.

Importing :func:`main` runs the top-level dispatcher. Individual subcommands
live in :mod:`cli.commands` and share helpers from :mod:`cli.log` and
:mod:`cli.env`.
"""

from .entry import main

__all__ = ["main"]
