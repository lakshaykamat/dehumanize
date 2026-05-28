"""Humanize pipeline: insert natural filler words into AI-sounding text.

This module exposes a pipeline of small, composable steps. The top-level
entry point is `humanize_pipeline(text, density="med", seed=None)`.

Pipeline stages:
    1. split text into lines
    2. classify each line (header-like vs. paragraph)
    3. split paragraphs into sentences
    4. transform each sentence (inject fillers)
    5. reassemble paragraphs and lines
"""

import random
import re

FILLERS = {
    "sentence_start": [
        "Consequently,", "Moreover,", "Furthermore,", "Notably,",
        "In particular,", "More specifically,", "In this context,",
        "From a theoretical standpoint,", "From a practical standpoint,",
        "Empirically,", "Conceptually,", "Architecturally,",
        "It is worth noting that", "It should be emphasized that",
        "One could argue that", "It follows that", "In effect,",
        "Crucially,", "By extension,", "Accordingly,",
        "As a consequence,", "In a similar vein,", "Equally important,",
        "It is often observed that", "Broadly construed,", "Strictly speaking,",
        "Conventionally,", "Historically,", "Of particular relevance,",
    ],
    "after_comma": [
        "in practice", "in principle", "by design",
        "in most implementations", "under typical workloads",
        "to a significant extent", "in the general case",
        "as is commonly observed", "as the literature suggests",
        "for all practical purposes", "in operational terms",
        "in architectural terms", "from a systems perspective",
    ],
    "before_conjunction": [
        "consequently", "conversely", "by contrast", "more importantly",
        "as a result", "in turn", "notably", "more precisely",
        "in other words", "that is to say",
    ],
    "mid_sentence_hedge": [
        "generally", "typically", "predominantly", "characteristically",
        "fundamentally", "intrinsically", "inherently", "ostensibly",
        "demonstrably", "arguably", "presumably", "purportedly",
        "structurally", "operationally",
    ],
    "sentence_tail": [
        ", in practice", ", in principle", ", by design",
        ", at scale", ", under realistic workloads",
        ", in production deployments", ", in the general case",
        ", as a matter of architectural convention",
        ", under most operating conditions",
        ", for all practical purposes",
    ],
}

DENSITY_PROBS = {
    "low":  {"start": 0.20, "comma": 0.25, "conj": 0.15, "hedge": 0.10, "tail": 0.08, "cap": 2, "gap": 6},
    "med":  {"start": 0.45, "comma": 0.45, "conj": 0.30, "hedge": 0.18, "tail": 0.18, "cap": 3, "gap": 5},
    "high": {"start": 0.85, "comma": 0.70, "conj": 0.55, "hedge": 0.30, "tail": 0.35, "cap": 4, "gap": 4},
}

CONJUNCTIONS = {"but", "and", "so", "or", "because", "however", "though"}

DENSITIES = tuple(DENSITY_PROBS.keys())

# matches indent + marker + space + body
#   markers: -, *, +, • – — ‣ ▪ ▸ ●, or numbered like "1.", "12)", "iv."
_LIST_RE = re.compile(
    r"^(?P<indent>\s*)"
    r"(?P<marker>[-*+•–—‣▪▸●]"
    r"|\d+[.)]"
    r"|[a-zA-Z][.)])"
    r"\s+(?P<body>.*\S)\s*$"
)

# matches a leading "**Label:** " bold-label prefix (label has no inner ** or newline)
_LABEL_RE = re.compile(r"^(\*\*[^*\n]+?:\*\*)\s+")

# matches a code-fence boundary line: ``` or ~~~ (optionally followed by lang)
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def split_list_marker(line: str):
    """Return (prefix, body) if the line starts with a list marker, else None.
    prefix preserves indentation + marker + the single separating space."""
    m = _LIST_RE.match(line)
    if not m:
        return None
    return f"{m.group('indent')}{m.group('marker')} ", m.group("body")


def split_label_prefix(text: str):
    """If text starts with `**Label:** `, return (label_prefix, body). Else None.
    The label_prefix INCLUDES the trailing space, so concatenation is lossless."""
    m = _LABEL_RE.match(text)
    if not m:
        return None
    return m.group(0), text[m.end():]


def is_header_like(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    if stripped.startswith("**") and stripped.endswith("**"):
        return True
    # Short labels with no sentence-like terminator (e.g. "Summary", "Conclusion").
    # `:` and `;` count as terminators so prose lines like "Common practices include:"
    # still flow through the humanizer.
    if len(stripped) < 60 and stripped[-1] not in ".!?:;":
        return True
    return False


def split_sentences(text: str):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


def pick_unique(category: str, used: set):
    candidates = [f for f in FILLERS[category] if f.lower() not in used]
    if not candidates:
        return None
    choice = random.choice(candidates)
    used.add(choice.lower())
    return choice


def humanize_sentence(sentence: str, probs: dict, used_fillers: set) -> str:
    words = sentence.split(" ")
    cap = probs["cap"]
    gap = probs["gap"]
    out = []
    fillers_used = 0
    last_filler_at = -gap

    def can_insert(idx: int) -> bool:
        return fillers_used < cap and (idx - last_filler_at) >= gap

    i = 0
    while i < len(words):
        word = words[i]

        clean = word.lower().strip(",.;:")
        if (
            clean in CONJUNCTIONS
            and i > 0
            and can_insert(i)
            and random.random() < probs["conj"]
        ):
            pick = pick_unique("before_conjunction", used_fillers)
            if pick:
                out.append(pick + ",")
                fillers_used += 1
                last_filler_at = i

        out.append(word)

        if word.endswith(",") and can_insert(i) and random.random() < probs["comma"]:
            pick = pick_unique("after_comma", used_fillers)
            if pick:
                out.append(pick)
                fillers_used += 1
                last_filler_at = i

        if (
            2 < i < len(words) - 2
            and not word.endswith(",")
            and can_insert(i)
            and random.random() < probs["hedge"]
        ):
            prev = words[i].lower().strip(",.;:")
            nxt = words[i + 1].lower().strip(",.;:") if i + 1 < len(words) else ""
            if prev not in {"the", "a", "an", "this", "that", "these", "those"} and nxt not in {"of", "to", "and", "or"}:
                pick = pick_unique("mid_sentence_hedge", used_fillers)
                if pick:
                    out.append(pick)
                    fillers_used += 1
                    last_filler_at = i

        i += 1

    result = " ".join(out)

    if random.random() < probs["start"]:
        starter = pick_unique("sentence_start", used_fillers)
        if starter:
            # Lowercase the first letter only for normally-capitalized words
            # (e.g. "Normalization" → "normalization"). Leave acronyms ("BCNF",
            # "SQL") and standalone capitals ("I") alone — detected by the
            # second char NOT being a lowercase letter.
            if (
                result
                and result[0].isupper()
                and result[1:2].islower()
                and not starter.rstrip().endswith((".", "!", "?"))
            ):
                result = result[0].lower() + result[1:]
            result = starter + " " + result

    if result and result[-1] in ".!?" and random.random() < probs["tail"]:
        tail = pick_unique("sentence_tail", used_fillers)
        if tail:
            original_end = result[-1]
            body = result[:-1]
            if tail.rstrip().endswith(("?", "!", ".")):
                result = body + tail
            else:
                result = body + tail + original_end

    return result


def humanize_paragraph(paragraph: str, probs: dict) -> str:
    sentences = split_sentences(paragraph)
    used_fillers: set = set()
    return " ".join(humanize_sentence(s, probs, used_fillers) for s in sentences)


def _humanize_body(text: str, probs: dict) -> str:
    """Humanize `text`, peeling any leading `**Label:**` so the label stays clean."""
    label_split = split_label_prefix(text)
    if label_split is None:
        return humanize_paragraph(text, probs)
    label_prefix, body = label_split
    return label_prefix + humanize_paragraph(body, probs)


def humanize_text(text: str, density: str = "med") -> str:
    if density not in DENSITY_PROBS:
        raise ValueError(f"Unknown density {density!r}. Choose from {DENSITIES}.")
    probs = DENSITY_PROBS[density]
    out_lines = []
    fence: str | None = None
    # Markdown structural lines (headings, table rows, stand-alone bold labels)
    # are preserved verbatim. Bullets and top-level lines starting with
    # `**Label:**` keep the label clean and humanize only the body after it.
    # Code fences (``` or ~~~) and everything between them are preserved
    # verbatim — fillers inside code would corrupt it.
    for line in text.splitlines():
        m = _FENCE_RE.match(line)
        if m:
            delim = m.group(1)
            if fence is None:
                fence = delim
            elif fence == delim:
                fence = None
            out_lines.append(line)
            continue
        if fence is not None:
            out_lines.append(line)
            continue
        if is_header_like(line):
            out_lines.append(line)
            continue
        marker_split = split_list_marker(line)
        if marker_split is not None:
            prefix, body = marker_split
            out_lines.append(prefix + _humanize_body(body, probs))
            continue
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        out_lines.append(indent + _humanize_body(stripped, probs))
    return "\n".join(out_lines)


def humanize_pipeline(text: str, density: str = "med", seed: int | None = None) -> str:
    """End-to-end pipeline: seed RNG, then run the humanize transform.

    Args:
        text: input text (one or more lines / paragraphs).
        density: "low" | "med" | "high" — how aggressively to inject fillers.
        seed: optional RNG seed for reproducible output.
    """
    if seed is not None:
        random.seed(seed)
    return humanize_text(text, density)
