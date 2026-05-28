"""`humanize` subcommand — inject filler words into a text file."""

from __future__ import annotations

import sys
import time

from humanize import DENSITIES, humanize_pipeline

from ..log import GREEN, RESET, fmt_duration, kv, log, ok, section, step


def add_parser(sub) -> None:
    p = sub.add_parser(
        "humanize",
        help="Humanize AI-sounding text.",
        description="Inject filler words, hedges, and connectors into text.",
    )
    p.add_argument("input", nargs="?", help="Input text file. Reads stdin if omitted.")
    p.add_argument("-o", "--output", help="Output file. Writes stdout if omitted.")
    p.add_argument("-d", "--density", choices=DENSITIES, default="high",
                   help="Filler injection density (default: high).")
    p.add_argument("-s", "--seed", type=int, default=None,
                   help="Random seed for reproducible output.")
    p.set_defaults(func=run)


def _read_text(path: str | None) -> str:
    if path is None:
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_text(path: str | None, text: str) -> None:
    if path is None:
        sys.stdout.write(text)
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def run(args) -> int:
    started = time.perf_counter()
    section("humanize")
    kv("input", args.input or "<stdin>")
    kv("output", args.output or "<stdout>")
    kv("density", args.density)
    kv("seed", args.seed if args.seed is not None else "(random)")

    step(1, 3, "reading input")
    try:
        text = _read_text(args.input)
    except FileNotFoundError:
        log(f"  err input file not found: {args.input}")
        return 1
    ok(f"{len(text)} chars, {len(text.splitlines())} line(s)")

    step(2, 3, "humanizing")
    result = humanize_pipeline(text, density=args.density, seed=args.seed)
    ok(f"{len(result.split())} words out")

    step(3, 3, "writing output")
    _write_text(args.output, result)
    ok(args.output or "<stdout>")

    log(f"\n{GREEN}done{RESET} in {fmt_duration(time.perf_counter() - started)}")
    return 0
