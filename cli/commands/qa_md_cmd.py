"""`qa-md` subcommand — ask OpenAI a list of questions and render Markdown."""

from __future__ import annotations

import json
import os
import time

from humanize import DENSITIES, humanize_pipeline
from qa import (
    DEFAULT_CONCURRENCY,
    DEFAULT_HUMANIZE_DENSITY,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TITLE,
    INFLATION_GUESS,
    MAX_RETRIES,
    MissingAPIKeyError,
    ProgressEvent,
    TokenUsage,
    build_md,
    generate_answers,
    make_client,
    validate_input,
)

from ..log import (
    CYAN,
    DIM,
    GREEN,
    RED,
    RESET,
    YELLOW,
    err,
    fmt_duration,
    kv,
    log,
    ok,
    section,
    step,
)


def add_parser(sub) -> None:
    p = sub.add_parser(
        "qa-md",
        help="Generate a Q&A Markdown file from a JSON list of questions.",
        description="Ask OpenAI a list of questions, humanize each answer, "
                    "and render a Markdown file.",
    )
    p.add_argument("input", help="JSON file: list of {question, words} objects.")
    p.add_argument("-o", "--output", required=True,
                   help="Output Markdown path (e.g. answers.md). A timestamp is appended.")
    p.add_argument("-m", "--model", default=DEFAULT_MODEL,
                   help=f"OpenAI model name (default: {DEFAULT_MODEL}).")
    p.add_argument("-t", "--title", default=DEFAULT_TITLE,
                   help=f"Document title (default: {DEFAULT_TITLE!r}).")
    p.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE,
                   help=f"Sampling temperature (default: {DEFAULT_TEMPERATURE}).")
    p.add_argument("--humanize-density", choices=DENSITIES,
                   default=DEFAULT_HUMANIZE_DENSITY,
                   help=f"Humanize density (default: {DEFAULT_HUMANIZE_DENSITY}).")
    p.add_argument("--humanize-seed", type=int, default=None,
                   help="Seed for the humanize step (reproducibility).")
    p.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY,
                   help=f"Max in-flight OpenAI requests (default: {DEFAULT_CONCURRENCY}).")
    p.set_defaults(func=run)


def _on_progress(ev: ProgressEvent) -> None:
    rng = ev.spec.range_str
    if ev.kind == "start":
        text = ev.spec.question
        snippet = text if len(text) <= 80 else text[:80] + "..."
        log(f"  {CYAN}q{ev.index}/{ev.total}{RESET} {snippet}")
        log(f"        {DIM}target range {rng} words (post-humanize){RESET}")
    elif ev.kind == "attempt":
        log(f"        {DIM}attempt {ev.attempt}: calling model...{RESET}")
    elif ev.kind == "ok":
        log(f"        {GREEN}ok{RESET} {ev.words} words in {rng} (attempt {ev.attempt})")
    elif ev.kind == "retry":
        log(f"        {YELLOW}miss{RESET} {ev.words} words (need {rng}) — recalibrating, retry")
    elif ev.kind == "give_up":
        if ev.words is None:
            log(f"        {RED}fail{RESET} API error")
        else:
            log(f"        {YELLOW}fallback{RESET} kept closest attempt ({ev.words} words, need {rng})")


def run(args) -> int:
    started = time.perf_counter()
    section("qa-md")
    kv("input", args.input)
    kv("output", args.output)
    kv("model", args.model)
    kv("temperature", args.temperature)
    kv("title", args.title)
    kv("humanize", f"on (density={args.humanize_density}, seed={args.humanize_seed})")
    kv("concurrency", args.concurrency)
    kv("max retries", MAX_RETRIES)

    total_steps = 4
    step(1, total_steps, "validating input")
    try:
        specs = validate_input(args.input)
    except FileNotFoundError:
        err(f"input file not found: {args.input}")
        return 1
    except (ValueError, json.JSONDecodeError) as e:
        err(f"invalid input JSON: {e}")
        return 1
    ok(f"{len(specs)} question(s) — word ranges {[s.range_str for s in specs]}")

    step(2, total_steps, "connecting to OpenAI")
    if not os.environ.get("OPENAI_API_KEY"):
        err("OPENAI_API_KEY is not set")
        return 2
    ok("API key found")

    try:
        client = make_client()
    except MissingAPIKeyError as e:
        err(str(e))
        return 2

    step(3, total_steps, f"generating answers (+ humanize density={args.humanize_density})")

    def transform(text: str) -> str:
        humanized = humanize_pipeline(text, density=args.humanize_density, seed=args.humanize_seed)
        log(
            f"\n{DIM}── ai answer ({len(text.split())} words) ──{RESET}\n"
            f"{text}\n"
            f"{DIM}── humanized ({len(humanized.split())} words) ──{RESET}\n"
            f"{humanized}\n"
        )
        return humanized
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
    ok(
        f"{len(qa_pairs)} answer(s) in {fmt_duration(time.perf_counter() - gen_start)}"
        + (f"  {RED}({failures} failed){RESET}" if failures else "")
    )

    step(total_steps, total_steps, "rendering Markdown")
    md_start = time.perf_counter()
    written_path = build_md(args.output, qa_pairs, title=args.title)
    ok(f"{written_path} — {len(qa_pairs)} Q&A in {fmt_duration(time.perf_counter() - md_start)}")

    _print_token_summary(gen_usage)
    log(f"\n{GREEN}done{RESET} in {fmt_duration(time.perf_counter() - started)}")
    return 0


def _print_token_summary(gen: TokenUsage) -> None:
    if gen.calls == 0:
        return
    section("tokens")
    log(
        f"  {GREEN}generate{RESET}  "
        f"{gen.prompt_tokens:,} prompt + "
        f"{gen.completion_tokens:,} completion = "
        f"{gen.total_tokens:,} total  "
        f"{DIM}({gen.calls} call{'s' if gen.calls != 1 else ''}){RESET}"
    )
