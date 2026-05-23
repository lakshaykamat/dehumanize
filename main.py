#!/usr/bin/env python3
"""Unified CLI. Dispatches to the humanize and qa-pdf pipelines.

Subcommands:
    humanize   Inject filler words into text to make it sound human.
    qa-pdf     Ask OpenAI a list of questions and render a clean PDF.

Examples:
    python main.py humanize para.txt
    python main.py humanize para.txt -d high -s 42 -o out.txt
    cat para.txt | python main.py humanize

    python main.py qa-pdf questions.txt -o answers.pdf
    python main.py qa-pdf questions.txt -o answers.pdf -m gpt-4o-mini -t "Interview Prep"
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from humanize import DENSITIES, humanize_pipeline
from qa_pdf import (
    DEFAULT_CONCURRENCY,
    DEFAULT_HUMANIZE_DENSITY,
    DEFAULT_MODEL,
    DEFAULT_REFORMAT,
    DEFAULT_TEMPERATURE,
    DEFAULT_TITLE,
    INFLATION_GUESS,
    MAX_RETRIES,
    MissingAPIKeyError,
    ProgressEvent,
    TokenUsage,
    build_pdf,
    generate_answers,
    make_client,
    reformat_pairs,
    validate_input,
)


# --- logging ----------------------------------------------------------------

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


def _log(msg: str = "") -> None:
    print(msg, file=sys.stderr)


def _section(title: str) -> None:
    bar = "─" * max(0, 60 - len(title) - 4)
    _log(f"\n{BOLD}── {title} {bar}{RESET}")


def _kv(key: str, value) -> None:
    _log(f"  {DIM}{key:<12}{RESET}{value}")


def _step(idx: int, total: int, label: str) -> None:
    _log(f"\n{BOLD}[{idx}/{total}]{RESET} {label}")


def _ok(msg: str) -> None:
    _log(f"  {GREEN}ok{RESET}  {msg}")


def _info(msg: str) -> None:
    _log(f"      {msg}")


def _warn(msg: str) -> None:
    _log(f"  {YELLOW}!!{RESET}  {msg}")


def _err(msg: str) -> None:
    _log(f"  {RED}err{RESET} {msg}")


def _fmt_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(seconds, 60)
    return f"{int(m)}m{s:04.1f}s"


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader: KEY=value lines, ignores blanks and '#' comments.
    Does not overwrite variables already set in the real environment.
    """
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# --- humanize subcommand -----------------------------------------------------

def _add_humanize(sub):
    p = sub.add_parser("humanize", help="Humanize AI-sounding text.")
    p.add_argument("input", nargs="?", help="Input text file. Reads stdin if omitted.")
    p.add_argument("-o", "--output", help="Output file. Writes stdout if omitted.")
    p.add_argument("-d", "--density", choices=DENSITIES, default="high",
                   help="Filler injection density (default: high).")
    p.add_argument("-s", "--seed", type=int, default=None,
                   help="Random seed for reproducible output.")
    p.set_defaults(func=_run_humanize)


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


def _run_humanize(args) -> int:
    started = time.perf_counter()
    _section("humanize")
    _kv("input", args.input or "<stdin>")
    _kv("output", args.output or "<stdout>")
    _kv("density", args.density)
    _kv("seed", args.seed if args.seed is not None else "(random)")

    _step(1, 3, "reading input")
    try:
        text = _read_text(args.input)
    except FileNotFoundError:
        _err(f"input file not found: {args.input}")
        return 1
    _ok(f"{len(text)} chars, {len(text.splitlines())} line(s)")

    _step(2, 3, "humanizing")
    result = humanize_pipeline(text, density=args.density, seed=args.seed)
    _ok(f"{len(result.split())} words out")

    _step(3, 3, "writing output")
    _write_text(args.output, result)
    _ok(args.output or "<stdout>")

    _log(f"\n{GREEN}done{RESET} in {_fmt_duration(time.perf_counter() - started)}")
    return 0


# --- qa-pdf subcommand -------------------------------------------------------

def _add_qa_pdf(sub):
    p = sub.add_parser("qa-pdf", help="Ask OpenAI a list of questions and render a PDF.")
    p.add_argument("input", help="JSON file: list of {question, words} objects.")
    p.add_argument("-o", "--output", required=True, help="Output PDF path.")
    p.add_argument("-m", "--model", default=DEFAULT_MODEL,
                   help=f"OpenAI model name (default: {DEFAULT_MODEL}).")
    p.add_argument("-t", "--title", default=DEFAULT_TITLE,
                   help="Title shown on the PDF header.")
    p.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE,
                   help=f"Sampling temperature (default: {DEFAULT_TEMPERATURE}).")
    p.add_argument("--humanize-density", choices=DENSITIES,
                   default=DEFAULT_HUMANIZE_DENSITY,
                   help=f"Humanize density (default: {DEFAULT_HUMANIZE_DENSITY}).")
    p.add_argument("--humanize-seed", type=int, default=None,
                   help="Seed for the humanize step (reproducibility).")
    p.add_argument("--no-reformat", dest="reformat", action="store_false",
                   help="Skip the AI formatting cleanup pass (default: on).")
    p.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY,
                   help=f"Max in-flight OpenAI requests "
                        f"(default: {DEFAULT_CONCURRENCY}).")
    p.set_defaults(func=_run_qa_pdf, reformat=DEFAULT_REFORMAT)


def _on_progress(ev: ProgressEvent) -> None:
    rng = ev.spec.range_str
    if ev.kind == "start":
        text = ev.spec.question
        snippet = text if len(text) <= 80 else text[:80] + "..."
        _log(f"  {CYAN}q{ev.index}/{ev.total}{RESET} {snippet}")
        _log(f"        {DIM}target range {rng} words (post-humanize){RESET}")
    elif ev.kind == "attempt":
        _log(f"        {DIM}attempt {ev.attempt}: calling model...{RESET}")
    elif ev.kind == "ok":
        _log(f"        {GREEN}ok{RESET} {ev.words} words in {rng} (attempt {ev.attempt})")
    elif ev.kind == "retry":
        _log(f"        {YELLOW}miss{RESET} {ev.words} words (need {rng}) — recalibrating, retry")
    elif ev.kind == "give_up":
        if ev.words is None:
            _log(f"        {RED}fail{RESET} API error")
        else:
            _log(f"        {YELLOW}fallback{RESET} kept closest attempt ({ev.words} words, need {rng})")


def _run_qa_pdf(args) -> int:
    started = time.perf_counter()
    _section("qa-pdf")
    _kv("input", args.input)
    _kv("output", args.output)
    _kv("model", args.model)
    _kv("temperature", args.temperature)
    _kv("title", args.title)
    _kv(
        "humanize",
        f"on (density={args.humanize_density}, seed={args.humanize_seed})",
    )
    _kv("reformat", "on (OpenAI)" if args.reformat else "off")
    _kv("concurrency", args.concurrency)
    _kv("max retries", MAX_RETRIES)

    total_steps = 5 if args.reformat else 4
    # step 1: validate
    _step(1, total_steps, "validating input")
    try:
        specs = validate_input(args.input)
    except FileNotFoundError:
        _err(f"input file not found: {args.input}")
        return 1
    except (ValueError, json.JSONDecodeError) as e:
        _err(f"invalid input JSON: {e}")
        return 1
    _ok(f"{len(specs)} question(s) — word ranges {[s.range_str for s in specs]}")

    # step 2: connect
    _step(2, total_steps, "connecting to OpenAI")
    if not os.environ.get("OPENAI_API_KEY"):
        _err("OPENAI_API_KEY is not set")
        return 2
    _ok("API key found")

    try:
        client = make_client()
    except MissingAPIKeyError as e:
        _err(str(e))
        return 2

    # step 3: generate
    _step(3, total_steps, f"generating answers (+ humanize density={args.humanize_density})")

    def transform(text: str) -> str:
        return humanize_pipeline(text, density=args.humanize_density, seed=args.humanize_seed)
    initial_inflation = INFLATION_GUESS.get(args.humanize_density, 1.0)

    gen_usage = TokenUsage()
    gen_start = time.perf_counter()
    qa_pairs = generate_answers(
        specs,
        client=client,
        model=args.model,
        temperature=args.temperature,
        progress=_on_progress,
        post_transform=transform,
        initial_inflation=initial_inflation,
        concurrency=args.concurrency,
        usage=gen_usage,
    )
    failures = sum(1 for _, a in qa_pairs if a.startswith("(Error generating answer:"))
    _ok(
        f"{len(qa_pairs)} answer(s) in {_fmt_duration(time.perf_counter() - gen_start)}"
        + (f"  {RED}({failures} failed){RESET}" if failures else "")
    )

    # step 4 (optional): AI reformat
    rf_usage = TokenUsage()
    if args.reformat:
        _step(4, total_steps, "reformatting answers (OpenAI cleanup)")
        rf_start = time.perf_counter()

        def _on_reformat(idx: int, tot: int, spec, before: int, after: int) -> None:
            text = spec.question
            snippet = text if len(text) <= 80 else text[:80] + "..."
            delta = after - before
            sign = "+" if delta >= 0 else ""
            _log(f"  {CYAN}q{idx}/{tot}{RESET} {snippet}")
            _log(f"        {GREEN}ok{RESET} words {before} → {after} ({sign}{delta})")

        qa_pairs = reformat_pairs(
            qa_pairs, client=client, model=args.model, progress=_on_reformat,
            concurrency=args.concurrency,
            usage=rf_usage,
        )
        _ok(f"reformatted {len(qa_pairs)} answer(s) in {_fmt_duration(time.perf_counter() - rf_start)}")

    # final step: pdf
    _step(total_steps, total_steps, "rendering PDF")
    pdf_start = time.perf_counter()
    written_path = build_pdf(args.output, qa_pairs, title=args.title)
    _ok(f"{written_path} — {len(qa_pairs)} Q&A in {_fmt_duration(time.perf_counter() - pdf_start)}")

    _print_token_summary(gen_usage, rf_usage)
    _log(f"\n{GREEN}done{RESET} in {_fmt_duration(time.perf_counter() - started)}")
    return 0


def _print_token_summary(gen: TokenUsage, rf: TokenUsage) -> None:
    """Print per-stage and total OpenAI token usage."""
    total = gen.merged(rf)
    rows = [("generate", gen), ("reformat", rf), ("total", total)]
    label_w = max(len(name) for name, _ in rows)
    num_w = max(len(f"{u.total_tokens:,}") for _, u in rows)
    _section("tokens")
    for name, u in rows:
        if u.calls == 0:
            continue
        color = GREEN if name == "total" else CYAN
        _log(
            f"  {color}{name:<{label_w}}{RESET}  "
            f"{u.prompt_tokens:>{num_w},} prompt + "
            f"{u.completion_tokens:>{num_w},} completion = "
            f"{u.total_tokens:>{num_w},} total  "
            f"{DIM}({u.calls} call{'s' if u.calls != 1 else ''}){RESET}"
        )


# --- interactive (non-dev) UX -----------------------------------------------

def _ask(prompt: str, default: str = "") -> str:
    """Ask for free-text input. Returns default if user hits Enter."""
    suffix = f" {DIM}[{default}]{RESET}" if default else ""
    try:
        val = input(f"  {prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        _log("")
        return default
    return val if val else default


def _ask_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = f" {DIM}[Y/n]{RESET}" if default else f" {DIM}[y/N]{RESET}"
    while True:
        try:
            v = input(f"  {prompt}{suffix}: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            _log("")
            return default
        if not v:
            return default
        if v in ("y", "yes"):
            return True
        if v in ("n", "no"):
            return False
        _log(f"  {YELLOW}please answer y or n{RESET}")


def _ask_menu(prompt: str, options: list[tuple[str, str]], default: str | None = None) -> str:
    """options: [(value, description), ...]. Returns the chosen value."""
    _log(f"\n  {BOLD}{prompt}{RESET}")
    default_idx = None
    for i, (val, desc) in enumerate(options, 1):
        is_default = (val == default)
        if is_default:
            default_idx = i
        marker = f"  {DIM}(default){RESET}" if is_default else ""
        _log(f"    {CYAN}{i}{RESET}) {val} — {DIM}{desc}{RESET}{marker}")
    while True:
        suffix = f" {DIM}[{default_idx}]{RESET}" if default_idx else ""
        try:
            v = input(f"  Pick a number{suffix}: ").strip()
        except (EOFError, KeyboardInterrupt):
            _log("")
            return default or options[0][0]
        if not v and default:
            return default
        if v.isdigit() and 1 <= int(v) <= len(options):
            return options[int(v) - 1][0]
        _log(f"  {YELLOW}please pick a number between 1 and {len(options)}{RESET}")


def _interactive_qa_pdf() -> int:
    _section("Q&A PDF — interactive setup")
    _log(f"{DIM}Press Enter to accept each [default].{RESET}\n")

    input_path = _ask("Path to questions JSON file", "q.json")
    output_path = _ask("Output PDF path", "answers.pdf")
    title = _ask("PDF title", DEFAULT_TITLE)
    model = _ask("OpenAI model", DEFAULT_MODEL)

    humanize_density = _ask_menu(
        "Humanize density",
        [
            ("low", "light filler injection"),
            ("med", "moderate filler injection"),
            ("high", "heavy filler injection — most evasive"),
        ],
        default=DEFAULT_HUMANIZE_DENSITY,
    )

    reformat_on = _ask_yes_no("Run AI formatting cleanup pass?", DEFAULT_REFORMAT)

    # confirm
    _section("review")
    _kv("input", input_path)
    _kv("output", output_path)
    _kv("title", title)
    _kv("model", model)
    _kv("humanize", f"on ({humanize_density})")
    _kv("reformat", "on" if reformat_on else "off")
    if not _ask_yes_no("\nRun with these settings?", True):
        _log(f"{YELLOW}cancelled.{RESET}")
        return 0

    args = argparse.Namespace(
        input=input_path,
        output=output_path,
        title=title,
        model=model,
        temperature=DEFAULT_TEMPERATURE,
        humanize_density=humanize_density,
        humanize_seed=None,
        reformat=reformat_on,
        concurrency=DEFAULT_CONCURRENCY,
    )
    return _run_qa_pdf(args)


def _interactive_humanize() -> int:
    _section("Humanize — interactive setup")
    _log(f"{DIM}Press Enter to accept each [default].{RESET}\n")

    input_path = _ask("Path to text file to humanize", "para.txt")
    output_path = _ask("Output text path (Enter for stdout)", "")
    density = _ask_menu(
        "Density",
        [
            ("low", "light filler injection"),
            ("med", "moderate filler injection"),
            ("high", "heavy filler injection — most evasive"),
        ],
        default="high",
    )
    seed_str = _ask("Random seed (Enter for random)", "")
    seed = int(seed_str) if seed_str.isdigit() else None

    _section("review")
    _kv("input", input_path)
    _kv("output", output_path or "<stdout>")
    _kv("density", density)
    _kv("seed", seed if seed is not None else "(random)")
    if not _ask_yes_no("\nRun with these settings?", True):
        _log(f"{YELLOW}cancelled.{RESET}")
        return 0

    args = argparse.Namespace(
        input=input_path,
        output=output_path or None,
        density=density,
        seed=seed,
    )
    return _run_humanize(args)


def _interactive() -> int:
    _section("dehumanize")
    _log("Welcome. This wizard will guide you step by step.\n")
    mode = _ask_menu(
        "What do you want to do?",
        [
            ("qa-pdf", "generate a Q&A PDF from a questions JSON (uses OpenAI)"),
            ("humanize", "add filler words to a text file"),
        ],
        default="qa-pdf",
    )
    return _interactive_qa_pdf() if mode == "qa-pdf" else _interactive_humanize()


# --- entry point -------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dehumanize",
        description=(
            "Run with no arguments for the interactive wizard, "
            "or pass a subcommand to script it."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=False)
    _add_humanize(sub)
    _add_qa_pdf(sub)
    return parser


def main(argv=None) -> int:
    _load_dotenv()
    if argv is None:
        argv = sys.argv[1:]

    # No args → interactive wizard
    if not argv:
        try:
            return _interactive()
        except KeyboardInterrupt:
            _log(f"\n{YELLOW}cancelled.{RESET}")
            return 130

    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        # they passed only global flags — drop to interactive
        try:
            return _interactive()
        except KeyboardInterrupt:
            _log(f"\n{YELLOW}cancelled.{RESET}")
            return 130
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
