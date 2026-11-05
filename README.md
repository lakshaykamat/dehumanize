# dehumanize

A small Python project with a web UI and CLI for humanizing text, generating Q&A Markdown, and converting Markdown to PDF.

## Install (Windows PowerShell)

Python 3.10+ is required. Python 3.12 is recommended for a smooth Windows install.

If Python 3.12 is not installed:

```powershell
winget install --exact --id Python.Python.3.12
```

From the project folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For Q&A generation, create `.env` beside `app.py`:

```powershell
notepad .env
```

Add your key and save:

```text
OPENAI_API_KEY=your-api-key
```

The API key is needed for Q&A generation. Humanize and PDF conversion do not need it.

## Web UI

```powershell
uvicorn app:app --reload --port 8000
```

Open http://127.0.0.1:8000. The Assignment page generates and downloads Markdown with visible progress. Use the CLI to convert the Markdown to PDF.

## CLI usage

Humanize a text file:

```powershell
python main.py humanize input.txt -o humanized.txt -d med
```

Create `questions.json` with a list of questions. `words` can be an exact count or a range:

```json
[
  { "question": "What is Python?", "words": 300 },
  { "question": "Explain Python lists.", "words": "400-500" }
]
```

Generate answers as Markdown:

```powershell
python main.py qa-md questions.json -o answers.md
```

The default model is `gpt-4o-mini`. Choose another model with `-m MODEL`.

Convert the generated Markdown file to PDF. Replace the example input with the timestamped filename created by the previous command:

```powershell
python main.py md-to-pdf answers-YYYY-MM-DD_HHMMSS.md -o answers.pdf
```

Run `python main.py --help` for all CLI options.
