# dehumanize

A two-part pipeline:

1. **humanize** — rewrites AI-sounding text to feel more human by injecting natural filler words, hedges, and sentence connectors at sensible break points.
2. **qa-pdf** — takes a JSON list of questions, asks OpenAI for answers, runs them through humanize, and renders a clean professional PDF.

## Project layout

```
.
├── main.py            # unified CLI dispatcher (subcommands: humanize, qa-pdf)
├── humanize.py        # humanize pipeline (pure library, no CLI)
├── qa_pdf/            # Q&A → PDF package
│   ├── config.py        # constants and defaults
│   ├── types.py         # QuestionSpec, ProgressEvent, MissingAPIKeyError
│   ├── loader.py        # JSON input parsing and validation
│   ├── prompts.py       # system + user prompt templates
│   ├── generator.py     # OpenAI client + per-question generation (retry/inflation)
│   ├── reformatter.py   # AI formatting cleanup pass
│   ├── pdf.py           # reportlab rendering
│   └── pipeline.py      # high-level orchestration
├── q.json             # sample questions input
├── answers.pdf        # sample output
├── requirements.txt   # third-party deps (only needed for qa-pdf)
└── README.md
```

Business logic lives in `humanize.py` and the `qa_pdf` package as importable pipelines. `main.py` is just the CLI surface — argument parsing, I/O, dispatch, and an interactive wizard.

## Requirements

- Python 3.10+ (uses `str | None` type hints).
- The humanize subcommand has **no third-party dependencies**.
- The qa-pdf subcommand needs `openai` and `reportlab`:

  ```bash
  pip install -r requirements.txt
  ```

## Usage

Run with **no arguments** for an interactive wizard:

```bash
python main.py
```

Or pass a subcommand to script it:

```bash
python main.py humanize ...
python main.py qa-pdf   ...
```

### Humanize

```bash
python main.py humanize input.txt                       # file in, stdout out
python main.py humanize input.txt -o out.txt            # file in, file out
python main.py humanize input.txt -d high -s 42         # high density, reproducible
cat input.txt | python main.py humanize                 # stdin
```

| Flag                            | Default  | Description                                            |
|---------------------------------|----------|--------------------------------------------------------|
| `input` (positional)            | stdin    | Path to input text file. Reads from stdin if omitted.  |
| `-o, --output PATH`             | stdout   | Output file. Writes to stdout if omitted.              |
| `-d, --density {low,med,high}`  | `high`   | How aggressively to inject fillers.                    |
| `-s, --seed N`                  | random   | Random seed for reproducible output.                   |

## Using the humanize pipeline from Python

`humanize.py` is a plain module — import and call it directly:

```python
from humanize import humanize_pipeline

text = open("input.txt").read()
out = humanize_pipeline(text, density="med", seed=7)
print(out)
```

Lower-level stages are also exported for finer control:

```python
from humanize import (
    DENSITIES,
    DENSITY_PROBS,
    split_sentences,
    humanize_sentence,
    humanize_paragraph,
    humanize_text,
)
```

### Pipeline stages

1. Split input into lines.
2. Classify each line as **header-like** (kept verbatim) or **paragraph**.
3. Split paragraphs into sentences.
4. Transform each sentence — insert sentence starters, after-comma phrases, pre-conjunction connectors, mid-sentence hedges, and sentence tails, subject to per-sentence caps and minimum gap rules.
5. Reassemble paragraphs and lines.

### Density profiles

| Density | Starter | After-comma | Pre-conj | Hedge | Tail | Cap | Gap |
|---------|--------:|------------:|---------:|------:|-----:|----:|----:|
| low     | 0.20    | 0.25        | 0.15     | 0.10  | 0.08 | 2   | 6   |
| med     | 0.45    | 0.45        | 0.30     | 0.18  | 0.18 | 3   | 5   |
| high    | 0.85    | 0.70        | 0.55     | 0.30  | 0.35 | 4   | 4   |

`cap` is the max fillers per sentence; `gap` is the minimum word distance between fillers.

## Reproducibility

Pass `--seed N` (CLI) or `seed=N` (Python) to get deterministic output for a given input.

---

## Q&A PDF (`qa-pdf` subcommand)

Take a list of questions, ask OpenAI for answers, humanize them, optionally do an AI cleanup pass, and render a clean professional PDF.

### Setup

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
```

A local `.env` file with `OPENAI_API_KEY=...` is also picked up automatically (existing env vars take precedence).

### Input format

A JSON file containing a list of `{question, words}` objects. `words` is the target answer length and accepts either:

- an integer (e.g. `450`) — the model is asked for `words ± 50`, or
- a range string `"min-max"` (e.g. `"400-500"`) — used directly as the target range.

The pipeline retries up to 3 times per question if the count is outside the range, then keeps the closest attempt.

```json
[
  { "question": "What is PEP8 and why does it matter?", "words": 450 },
  { "question": "Explain threads vs. processes.",       "words": "400-500" }
]
```

Plain strings are also accepted as items (they default to ~450 words).

### Prompting behavior

- One OpenAI call per question (never bundled).
- Answers are written in very basic English, professional tone, as plain paragraphs of running prose — no headings, bullets, bold, or markdown.
- If an answer is outside the requested word range, the pipeline retries with feedback (up to 3 times) and keeps the closest attempt if it still fails.
- Each answer is then passed through the humanize step (always on; only the density is configurable), and by default also through an AI-driven formatting cleanup pass.

### Usage

```bash
python main.py qa-pdf q.json -o answers.pdf
python main.py qa-pdf q.json -o answers.pdf -m gpt-4o-mini -t "Interview Prep" --author "L. Kamat"
python main.py qa-pdf q.json -o answers.pdf --humanize-density low --no-reformat
```

| Flag                              | Default                  | Description                                              |
|-----------------------------------|--------------------------|----------------------------------------------------------|
| `input` (positional)              | —                        | JSON file: list of `{question, words}` objects.          |
| `-o, --output PATH`               | required                 | Output PDF path.                                         |
| `-m, --model NAME`                | `gpt-4o-mini`            | OpenAI model to use.                                     |
| `-t, --title TEXT`                | `Questions & Answers`    | Title shown at the top of the PDF.                       |
| `--author TEXT`                   | none                     | Optional subtitle line under the title.                  |
| `--temperature FLOAT`             | `0.3`                    | Sampling temperature.                                    |
| `--humanize-density {low,med,high}` | `high`                 | Density for the (always-on) humanize pass.               |
| `--humanize-seed N`               | random                   | Seed for the humanize pass (reproducibility).            |
| `--no-reformat`                   | reformat on              | Skip the AI formatting cleanup pass.                     |

### Output style

- Letter-size pages with generous margins.
- Bold numbered question heading in deep blue.
- Justified body answer in dark slate.
- Subtle horizontal rule between Q&A blocks.
- Date and page number in the footer.

## Using the qa-pdf pipeline from Python

The `qa_pdf` package re-exports its public surface at the top level:

```python
from qa_pdf import (
    make_client,
    validate_input,
    generate_answers,
    reformat_pairs,
    build_pdf,
    questions_to_pdf,   # high-level one-shot orchestrator
)

questions_to_pdf("q.json", "answers.pdf", title="Interview Prep")
```
