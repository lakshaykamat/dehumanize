"""`qa-md` subcommand — ask OpenAI a list of questions and render Markdown."""

from __future__ import annotations

import argparse
import json
import os
import time

from humanize import DENSITIES, humanize_pipeline
from qa import (
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
    build_md,
    generate_answers,
    make_client,
    reformat_pairs,
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
from ..prompts import ask, ask_file, ask_menu, ask_yes_no


def add_parser(sub) -> None:
    p = sub.add_parser(
        "qa-md",
        help="Ask OpenAI a list of questions and render a Markdown file.",
    )
    p.add_argument("input", help="JSON file: list of {question, words} objects.")
    p.add_argument("-o", "--output", required=True, help="Output Markdown path (e.g. answers.md).")
    p.add_argument("-m", "--model", default=DEFAULT_MODEL,
                   help=f"OpenAI model name (default: {DEFAULT_MODEL}).")
    p.add_argument("-t", "--title", default=DEFAULT_TITLE,
                   help="Title shown at the top of the Markdown file.")
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
    p.set_defaults(func=run, reformat=DEFAULT_REFORMAT)


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
    kv("reformat", "on (OpenAI)" if args.reformat else "off")
    kv("concurrency", args.concurrency)
    kv("max retries", MAX_RETRIES)

    total_steps = 5 if args.reformat else 4
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
    ok(
        f"{len(qa_pairs)} answer(s) in {fmt_duration(time.perf_counter() - gen_start)}"
        + (f"  {RED}({failures} failed){RESET}" if failures else "")
    )

    rf_usage = TokenUsage()
    if args.reformat:
        step(4, total_steps, "reformatting answers (OpenAI cleanup)")
        rf_start = time.perf_counter()

        def _on_reformat(idx: int, tot: int, spec, before: int, after: int) -> None:
            text = spec.question
            snippet = text if len(text) <= 80 else text[:80] + "..."
            delta = after - before
            sign = "+" if delta >= 0 else ""
            log(f"  {CYAN}q{idx}/{tot}{RESET} {snippet}")
            log(f"        {GREEN}ok{RESET} words {before} → {after} ({sign}{delta})")

        qa_pairs = reformat_pairs(
            qa_pairs, client=client, model=args.model, progress=_on_reformat,
            concurrency=args.concurrency,
            usage=rf_usage,
        )
        ok(f"reformatted {len(qa_pairs)} answer(s) in {fmt_duration(time.perf_counter() - rf_start)}")

    step(total_steps, total_steps, "rendering Markdown")
    md_start = time.perf_counter()
    written_path = build_md(args.output, qa_pairs, title=args.title)
    ok(f"{written_path} — {len(qa_pairs)} Q&A in {fmt_duration(time.perf_counter() - md_start)}")

    _print_token_summary(gen_usage, rf_usage)
    log(f"\n{GREEN}done{RESET} in {fmt_duration(time.perf_counter() - started)}")
    return 0


def _print_token_summary(gen: TokenUsage, rf: TokenUsage) -> None:
    total = gen.merged(rf)
    rows = [("generate", gen), ("reformat", rf), ("total", total)]
    label_w = max(len(name) for name, _ in rows)
    num_w = max(len(f"{u.total_tokens:,}") for _, u in rows)
    section("tokens")
    for name, u in rows:
        if u.calls == 0:
            continue
        color = GREEN if name == "total" else CYAN
        log(
            f"  {color}{name:<{label_w}}{RESET}  "
            f"{u.prompt_tokens:>{num_w},} prompt + "
            f"{u.completion_tokens:>{num_w},} completion = "
            f"{u.total_tokens:>{num_w},} total  "
            f"{DIM}({u.calls} call{'s' if u.calls != 1 else ''}){RESET}"
        )


def interactive() -> int:
    section("Q&A Markdown — interactive setup")
    log("Press Enter to accept each [default].\n")

    input_path = ask_file(
        "Pick the questions JSON file",
        ["*.json"],
        exclude_globs=["vercel.json", "package.json", "package-lock.json", "tsconfig*.json"],
    )
    default_output = f"{os.path.splitext(os.path.basename(input_path))[0]}-answers.md"
    output_path = ask("Output Markdown path", default_output)
    title = ask("Document title", DEFAULT_TITLE)
    model = ask("OpenAI model", DEFAULT_MODEL)

    humanize_density = ask_menu(
        "Humanize density",
        [
            ("low", "light filler injection"),
            ("med", "moderate filler injection"),
            ("high", "heavy filler injection — most evasive"),
        ],
        default=DEFAULT_HUMANIZE_DENSITY,
    )

    reformat_on = ask_yes_no("Run AI formatting cleanup pass?", DEFAULT_REFORMAT)

    section("review")
    kv("input", input_path)
    kv("output", output_path)
    kv("title", title)
    kv("model", model)
    kv("humanize", f"on ({humanize_density})")
    kv("reformat", "on" if reformat_on else "off")
    if not ask_yes_no("\nRun with these settings?", True):
        log(f"{YELLOW}cancelled.{RESET}")
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
    return run(args)
