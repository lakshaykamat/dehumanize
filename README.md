# dehumanize

A small CLI with three composable subcommands:

1. **humanize** — rewrites AI-sounding text to feel more human by injecting natural filler words, hedges, and sentence connectors.
2. **qa-md** — takes a JSON list of questions, asks OpenAI for answers, humanizes them, and writes a Markdown file.
3. **md-to-pdf** — renders a Markdown file as a PDF (A4 / Times New Roman 12pt / 0.5in margins / justified by default).

`qa-md` and `md-to-pdf` are intentionally split so you can edit the generated Markdown before rendering the PDF.

## Project layout

```
.
├── main.py            # CLI entry point (dispatches to `cli` package)
├── cli/               # argparse glue, subcommand handlers, logging
├── humanize.py        # humanize pipeline (importable library)
├── qa/                # Q&A → Markdown → PDF package
├── q.json             # sample questions input
├── requirements.txt
└── README.md
```

## Requirements

- Python 3.10+ (uses `str | None` type hints).
- `humanize` has **no third-party dependencies**.
- `qa-md` and `md-to-pdf` need `openai` and `reportlab`:

  ```bash
  pip install -r requirements.txt
  ```

- `qa-md` needs `OPENAI_API_KEY` in the environment or in a local `.env` file (existing env vars take precedence).

## Quick start

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...

# end-to-end: questions JSON → answers Markdown → PDF
python main.py qa-md q.json -o answers.md
python main.py md-to-pdf answers-*.md -o answers.pdf
```

All commands write progress to **stderr** and the final artifact to the path you pass (or stdout for `humanize` with no `-o`). Exit codes: `0` ok, `1` bad input, `2` missing API key.

---

## `humanize`

Inject filler words, hedges, and connectors into a text file.

```
python main.py humanize [INPUT] [-o OUTPUT] [-d {low,med,high}] [-s SEED]
```

| Flag                           | Default | Description                                           |
|--------------------------------|---------|-------------------------------------------------------|
| `input` (positional)           | stdin   | Path to input text file. Reads from stdin if omitted. |
| `-o, --output PATH`            | stdout  | Output file. Writes to stdout if omitted.             |
| `-d, --density {low,med,high}` | `high`  | How aggressively to inject fillers.                   |
| `-s, --seed N`                 | random  | Random seed for reproducible output.                  |

Examples:

```bash
python main.py humanize input.txt                    # file in, stdout out
python main.py humanize input.txt -o out.txt         # file in, file out
python main.py humanize input.txt -d high -s 42      # high density, reproducible
cat input.txt | python main.py humanize              # stdin
```

### Using the humanize pipeline from Python

```python
from humanize import humanize_pipeline

out = humanize_pipeline(open("input.txt").read(), density="med", seed=7)
print(out)
```

Lower-level stages are also exported:

```python
from humanize import (
    DENSITIES, DENSITY_PROBS,
    split_sentences, humanize_sentence, humanize_paragraph, humanize_text,
)
```

### Density profiles

| Density | Starter | After-comma | Pre-conj | Hedge | Tail | Cap | Gap |
|---------|--------:|------------:|---------:|------:|-----:|----:|----:|
| low     | 0.20    | 0.25        | 0.15     | 0.10  | 0.08 | 2   | 6   |
| med     | 0.45    | 0.45        | 0.30     | 0.18  | 0.18 | 3   | 5   |
| high    | 0.85    | 0.70        | 0.55     | 0.30  | 0.35 | 4   | 4   |

`cap` is the max fillers per sentence; `gap` is the minimum word distance between fillers.

---

## `qa-md`

Ask OpenAI a list of questions, humanize each answer, and write a Markdown file. A timestamp is appended to the output filename (e.g. `answers-2026-05-28_101119.md`).

```
python main.py qa-md INPUT -o OUTPUT
                     [-m MODEL] [-t TITLE] [--temperature FLOAT]
                     [--humanize-density {low,med,high}] [--humanize-seed N]
                     [--concurrency N]
```

| Flag                                  | Default                 | Description                                                            |
|---------------------------------------|-------------------------|------------------------------------------------------------------------|
| `input` (positional)                  | required                | JSON file: list of `{question, words}` objects.                        |
| `-o, --output PATH`                   | required                | Output Markdown path (timestamp appended).                             |
| `-m, --model NAME`                    | `gpt-5.2`               | OpenAI model to use.                                                   |
| `-t, --title TEXT`                    | `Questions & Answers`   | Title at the top of the document.                                      |
| `--temperature FLOAT`                 | `0.3`                   | Sampling temperature.                                                  |
| `--humanize-density {low,med,high}`   | `high`                  | Density for the (always-on) humanize pass.                             |
| `--humanize-seed N`                   | random                  | Seed for the humanize pass.                                            |
| `--concurrency N`                     | `10`                    | Max in-flight OpenAI requests.                                         |

### Input format

A JSON list of `{question, words}` objects. `words` accepts either an integer (`450` → asks for `words ± 50`) or a range string (`"400-500"`):

```json
[
  { "question": "What is PEP8 and why does it matter?", "words": 450 },
  { "question": "Explain threads vs. processes.",       "words": "400-500" }
]
```

Plain strings are also accepted (they default to ~450 words). The pipeline retries up to 3 times per question if the count falls outside the range, then keeps the closest attempt.

### Examples

```bash
# minimal
python main.py qa-md q.json -o answers.md

# tune density, model, concurrency
python main.py qa-md q.json -o answers.md \
  -m gpt-4o-mini --humanize-density low --concurrency 4 \
  -t "Interview Prep"
```

### Output

The generated `.md` opens with `# <title>`, then numbered `## N. <question>` sections with the humanized answer underneath.

---

## `md-to-pdf`

Render any Markdown file (typically `qa-md` output) as PDF. No API calls. A timestamp is appended to the output filename.

```
python main.py md-to-pdf INPUT -o OUTPUT [-t TITLE] [style flags ...]
```

| Flag                              | Default      | Description                                                |
|-----------------------------------|--------------|------------------------------------------------------------|
| `input` (positional)              | required     | Input Markdown file.                                       |
| `-o, --output PATH`               | required     | Output PDF path (timestamp appended).                      |
| `-t, --title TEXT`                | (from H1)    | Override the document title.                               |
| `--page-size {letter,a4,legal,a3,a5}` | `a4`     | Page size.                                                 |
| `--margin INCHES`                 | `0.5`        | Page margin, all sides.                                    |
| `--font {helvetica,times,courier}`| `times`      | Font family.                                               |
| `--body-size PT`                  | `12.0`       | Body text size.                                            |
| `--line-spacing MULT`             | `1.43`       | Line-height multiplier.                                    |
| `--title-size PT`                 | `24.0`       | Title size.                                                |
| `--question-size PT`              | `13.5`       | Question heading size.                                     |
| `--h3-size PT`                    | `11.5`       | H3 subheading size.                                        |
| `--h4-size PT`                    | `10.5`       | H4 subheading size.                                        |
| `--text-color HEX`                | `#000000`    | Hex color for all text.                                    |
| `--separator-color HEX`           | `#e2e8f0`    | Hex color for the line between questions.                  |
| `--align {justify,left}`          | `justify`    | Answer paragraph alignment.                                |
| `--no-separator`                  | off          | Hide the horizontal rule between questions.                |

Defaults reproduce the standard institutional layout: A4, Times New Roman 12pt, 0.5" margins, justified.

Examples:

```bash
python main.py md-to-pdf answers.md -o answers.pdf
python main.py md-to-pdf answers.md -o answers.pdf -t "Final Submission"
python main.py md-to-pdf notes.md   -o notes.pdf \
  --font helvetica --body-size 11 --align left --no-separator
```

---

## Reproducibility

Pass `--seed N` (`humanize`) or `--humanize-seed N` (`qa-md`) for deterministic output for a given input.

## Using the qa pipeline from Python

```python
from qa import (
    make_client, validate_input, generate_answers,
    build_md, md_to_pdf, questions_to_pdf,
)

questions_to_pdf("q.json", "answers.pdf", title="Interview Prep")
```
