"""Interactive prompt helpers: free-text, yes/no, numbered menus, file picker."""

from __future__ import annotations

from pathlib import Path

from .log import BOLD, CYAN, DIM, RESET, YELLOW, log


_SKIP_DIRS = {"__pycache__", "node_modules", ".git", ".venv", "venv", "dist", "build"}
_MAX_MATCHES = 20


def ask(prompt: str, default: str = "") -> str:
    """Ask for free-text input. Returns `default` if the user hits Enter."""
    suffix = f" {DIM}[{default}]{RESET}" if default else ""
    try:
        val = input(f"  {prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        log("")
        return default
    return val if val else default


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = f" {DIM}[Y/n]{RESET}" if default else f" {DIM}[y/N]{RESET}"
    while True:
        try:
            v = input(f"  {prompt}{suffix}: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            log("")
            return default
        if not v:
            return default
        if v in ("y", "yes"):
            return True
        if v in ("n", "no"):
            return False
        log(f"  {YELLOW}please answer y or n{RESET}")


def _human_size(n: int) -> str:
    for unit in ("B", "K", "M", "G"):
        if n < 1024:
            return f"{n}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}T"


def _scan_files(
    patterns: list[str],
    roots: list[str],
    exclude_globs: list[str] | None = None,
) -> list[Path]:
    """Return up to _MAX_MATCHES files matching any of `patterns` under `roots`
    (one level deep). Sorted by mtime descending, then path. Hidden dirs and
    common build dirs are skipped. Files whose name matches any pattern in
    `exclude_globs` (matched against the filename only) are skipped."""
    exclude_globs = exclude_globs or []
    seen: set[Path] = set()
    matches: list[Path] = []

    def keep(p: Path) -> bool:
        if not p.is_file() or p in seen:
            return False
        return not any(p.match(g) for g in exclude_globs)

    for r in roots:
        base = Path(r)
        if not base.is_dir():
            continue
        for pat in patterns:
            for p in base.glob(pat):
                if keep(p):
                    seen.add(p)
                    matches.append(p)
        for sub in base.iterdir():
            if not sub.is_dir() or sub.name.startswith(".") or sub.name in _SKIP_DIRS:
                continue
            for pat in patterns:
                for p in sub.glob(pat):
                    if keep(p):
                        seen.add(p)
                        matches.append(p)
    matches.sort(key=lambda p: (-p.stat().st_mtime, str(p)))
    return matches[:_MAX_MATCHES]


def ask_file(
    prompt: str,
    patterns: list[str],
    roots: list[str] | None = None,
    exclude_globs: list[str] | None = None,
) -> str:
    """Show a numbered menu of files matching `patterns` (glob, e.g. `*.json`).
    Searches the current directory and its immediate subdirectories. Hitting
    Enter selects the first match (most recently modified). If no files match
    or the user picks the final "type a path" entry, falls back to free text.
    `exclude_globs` lets the caller hide noise files (e.g. `vercel.json`,
    `README*.md`) — matched against each candidate's filename only.
    """
    roots = roots or ["."]
    matches = _scan_files(patterns, roots, exclude_globs)
    if not matches:
        return ask(prompt, "")

    log(f"\n  {BOLD}{prompt}{RESET}")
    for i, p in enumerate(matches, 1):
        marker = f"  {DIM}(default){RESET}" if i == 1 else ""
        log(f"    {CYAN}{i}{RESET}) {p}  {DIM}({_human_size(p.stat().st_size)}){RESET}{marker}")
    type_idx = len(matches) + 1
    log(f"    {CYAN}{type_idx}{RESET}) {DIM}type a custom path…{RESET}")
    while True:
        try:
            v = input(f"  Pick a number {DIM}[1]{RESET}: ").strip()
        except (EOFError, KeyboardInterrupt):
            log("")
            return str(matches[0])
        if not v:
            return str(matches[0])
        if v.isdigit():
            n = int(v)
            if 1 <= n <= len(matches):
                return str(matches[n - 1])
            if n == type_idx:
                return ask("File path", "")
        log(f"  {YELLOW}please pick a number between 1 and {type_idx}{RESET}")


def ask_menu(prompt: str, options: list[tuple[str, str]], default: str | None = None) -> str:
    """Display a numbered menu and return the chosen value.

    `options` is `[(value, description), ...]`. If `default` matches one of the
    values, hitting Enter selects it.
    """
    log(f"\n  {BOLD}{prompt}{RESET}")
    default_idx = None
    for i, (val, desc) in enumerate(options, 1):
        is_default = (val == default)
        if is_default:
            default_idx = i
        marker = f"  {DIM}(default){RESET}" if is_default else ""
        log(f"    {CYAN}{i}{RESET}) {val} — {DIM}{desc}{RESET}{marker}")
    while True:
        suffix = f" {DIM}[{default_idx}]{RESET}" if default_idx else ""
        try:
            v = input(f"  Pick a number{suffix}: ").strip()
        except (EOFError, KeyboardInterrupt):
            log("")
            return default or options[0][0]
        if not v and default:
            return default
        if v.isdigit() and 1 <= int(v) <= len(options):
            return options[int(v) - 1][0]
        log(f"  {YELLOW}please pick a number between 1 and {len(options)}{RESET}")
