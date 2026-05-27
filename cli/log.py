"""Terminal logging primitives: ANSI colours, sectioned output, step headers.

All output goes to stderr so subcommands writing stdout (e.g. `humanize` with
no `-o`) stay pipe-clean.
"""

from __future__ import annotations

import sys


_USE_COLOR = sys.stderr.isatty()


def _c(code: str) -> str:
    return code if _USE_COLOR else ""


BOLD = _c("\033[1m")
DIM = _c("\033[2m")
RED = _c("\033[31m")
GREEN = _c("\033[32m")
YELLOW = _c("\033[33m")
BLUE = _c("\033[34m")
CYAN = _c("\033[36m")
RESET = _c("\033[0m")


def log(msg: str = "") -> None:
    print(msg, file=sys.stderr)


def section(title: str) -> None:
    bar = "─" * max(0, 60 - len(title) - 4)
    log(f"\n{BOLD}── {title} {bar}{RESET}")


def kv(key: str, value) -> None:
    log(f"  {DIM}{key:<12}{RESET}{value}")


def step(idx: int, total: int, label: str) -> None:
    log(f"\n{BOLD}[{idx}/{total}]{RESET} {label}")


def ok(msg: str) -> None:
    log(f"  {GREEN}ok{RESET}  {msg}")


def info(msg: str) -> None:
    log(f"      {msg}")


def warn(msg: str) -> None:
    log(f"  {YELLOW}!!{RESET}  {msg}")


def err(msg: str) -> None:
    log(f"  {RED}err{RESET} {msg}")


def fmt_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(seconds, 60)
    return f"{int(m)}m{s:04.1f}s"
