"""FastAPI web app exposing the humanize and qa-pdf pipelines.

Run:
    uvicorn app:app --reload --port 8000

Endpoints:
    GET  /                 redirect → /humanize
    GET  /humanize         humanize form
    POST /humanize         form submit → result page
    GET  /assignment       assignment form
    POST /assignment       form submit → PDF download
    POST /api/humanize     JSON in/out
    POST /api/assignment   JSON in, PDF binary out
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import time
from pathlib import Path

from typing import List

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from humanize import DENSITIES, humanize_pipeline
from qa_pdf import (
    DEFAULT_CONCURRENCY,
    DEFAULT_HUMANIZE_DENSITY,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TITLE,
    INFLATION_GUESS,
    MissingAPIKeyError,
    ProgressEvent,
    TokenUsage,
    build_pdf,
    generate_answers,
    make_client,
    reformat_pairs,
    read_questions,
)
from qa_pdf.types import QuestionSpec


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-5s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("app")


BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv(path: Path = BASE_DIR / ".env") -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

app = FastAPI(title="AI Detector — humanize + Q&A PDF")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

static_dir = BASE_DIR / "static"
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# --- request models ---------------------------------------------------------


class HumanizeRequest(BaseModel):
    text: str = Field(..., min_length=1)
    density: str = Field(default="high")
    seed: int | None = None


class QuestionItem(BaseModel):
    question: str
    words: str | int


class QaPdfRequest(BaseModel):
    questions: list[QuestionItem]
    title: str = DEFAULT_TITLE
    model: str = DEFAULT_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    humanize_density: str = DEFAULT_HUMANIZE_DENSITY
    humanize_seed: int | None = None
    reformat: bool = True
    concurrency: int = DEFAULT_CONCURRENCY


# --- helpers ----------------------------------------------------------------


def _parse_questions_payload(data) -> list[QuestionSpec]:
    """Re-use the loader's validation against an in-memory list."""
    if not isinstance(data, list) or not data:
        raise ValueError("questions must be a non-empty JSON array.")
    # Write to a temp file so we can leverage the existing validator
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8")
    try:
        json.dump(data, tmp)
        tmp.flush()
        tmp.close()
        return read_questions(tmp.name)
    finally:
        os.unlink(tmp.name)


def _on_progress(ev: ProgressEvent) -> None:
    snippet = ev.spec.question
    if len(snippet) > 60:
        snippet = snippet[:60] + "…"
    rng = ev.spec.range_str
    tag = f"[q{ev.index}/{ev.total}]"
    if ev.kind == "start":
        log.info("%s start  %s  (target %s words)", tag, snippet, rng)
    elif ev.kind == "attempt":
        log.info("%s attempt %d  calling model…", tag, ev.attempt)
    elif ev.kind == "ok":
        log.info("%s ok      %d words in %s (attempt %d)", tag, ev.words, rng, ev.attempt)
    elif ev.kind == "retry":
        log.warning("%s miss    %d words (need %s) — retrying", tag, ev.words, rng)
    elif ev.kind == "give_up":
        if ev.words is None:
            log.error("%s fail    API error", tag)
        else:
            log.warning("%s fallback kept closest (%d words, need %s)", tag, ev.words, rng)


def _on_reformat(idx: int, tot: int, spec, before: int, after: int) -> None:
    snippet = spec.question[:60] + ("…" if len(spec.question) > 60 else "")
    delta = after - before
    sign = "+" if delta >= 0 else ""
    log.info("[reformat %d/%d] %s  words %d → %d (%s%d)", idx, tot, snippet, before, after, sign, delta)


def _run_qa_pdf_sync(
    specs: list[QuestionSpec],
    *,
    out_path: str,
    title: str,
    model: str,
    temperature: float,
    humanize_density: str,
    humanize_seed: int | None,
    reformat: bool,
    concurrency: int,
) -> str:
    """Synchronous end-to-end PDF generation. Runs off the event loop.
    Returns the actual path written (build_pdf timestamps the filename)."""
    log.info(
        "pdf-gen start  questions=%d  model=%s  density=%s  reformat=%s  concurrency=%d",
        len(specs), model, humanize_density, reformat, concurrency,
    )
    t0 = time.perf_counter()
    client = make_client()

    def transform(text: str) -> str:
        return humanize_pipeline(text, density=humanize_density, seed=humanize_seed)

    initial_inflation = INFLATION_GUESS.get(humanize_density, 1.0)

    gen_usage = TokenUsage()
    gen_t0 = time.perf_counter()
    qa_pairs = generate_answers(
        specs,
        client=client,
        model=model,
        temperature=temperature,
        progress=_on_progress,
        post_transform=transform,
        initial_inflation=initial_inflation,
        concurrency=concurrency,
        usage=gen_usage,
    )
    failures = sum(1 for _, a in qa_pairs if a.startswith("(Error generating answer:"))
    log.info(
        "generate done  %d answer(s) in %.1fs  tokens=%d  failures=%d",
        len(qa_pairs), time.perf_counter() - gen_t0, gen_usage.total_tokens, failures,
    )

    if reformat:
        rf_usage = TokenUsage()
        rf_t0 = time.perf_counter()
        qa_pairs = reformat_pairs(
            qa_pairs, client=client, model=model,
            progress=_on_reformat,
            concurrency=concurrency,
            usage=rf_usage,
        )
        log.info(
            "reformat done  %d answer(s) in %.1fs  tokens=%d",
            len(qa_pairs), time.perf_counter() - rf_t0, rf_usage.total_tokens,
        )

    written = build_pdf(out_path, qa_pairs, title=title)
    size = os.path.getsize(written) if os.path.isfile(written) else 0
    log.info(
        "pdf-gen done   path=%s  size=%d bytes  elapsed=%.1fs",
        written, size, time.perf_counter() - t0,
    )
    return written


# --- HTML pages -------------------------------------------------------------


@app.get("/")
async def index():
    return RedirectResponse(url="/humanize", status_code=307)


@app.get("/humanize", response_class=HTMLResponse)
async def humanize_page(request: Request):
    return templates.TemplateResponse(
        request,
        "humanize.html",
        {"densities": DENSITIES, "default_density": "high"},
    )


@app.post("/humanize", response_class=HTMLResponse)
async def humanize_submit(
    request: Request,
    text: str = Form(...),
    density: str = Form("high"),
    seed: str = Form(""),
):
    if density not in DENSITIES:
        raise HTTPException(400, f"invalid density (allowed: {list(DENSITIES)})")
    seed_int = int(seed) if seed.strip().isdigit() else None
    result = humanize_pipeline(text, density=density, seed=seed_int)
    return templates.TemplateResponse(
        request,
        "humanize.html",
        {
            "densities": DENSITIES,
            "default_density": density,
            "input_text": text,
            "result": result,
            "seed": seed,
        },
    )


@app.get("/assignment", response_class=HTMLResponse)
async def assignment_page(request: Request):
    return templates.TemplateResponse(
        request,
        "assignment.html",
        {
            "defaults": {
                "title": DEFAULT_TITLE,
            },
        },
    )


@app.post("/assignment")
async def assignment_submit(
    question: List[str] = Form(...),
    words: List[str] = Form(...),
    title: str = Form(DEFAULT_TITLE),
):
    if len(question) != len(words):
        raise HTTPException(400, "question and words field counts do not match.")

    data = [
        {"question": q.strip(), "words": w.strip()}
        for q, w in zip(question, words)
        if q.strip() and w.strip()
    ]
    if not data:
        raise HTTPException(400, "Add at least one question with a word count.")

    try:
        specs = _parse_questions_payload(data)
    except ValueError as e:
        log.warning("assignment validation failed: %s", e)
        raise HTTPException(400, str(e))

    log.info(
        "assignment request  title=%r  questions=%d  ranges=%s",
        title, len(specs), [s.range_str for s in specs],
    )

    out_dir = tempfile.mkdtemp(prefix="assignment-")
    stub_path = os.path.join(out_dir, "assignment.pdf")

    try:
        written_path = await asyncio.to_thread(
            _run_qa_pdf_sync,
            specs,
            out_path=stub_path,
            title=title,
            model=DEFAULT_MODEL,
            temperature=DEFAULT_TEMPERATURE,
            humanize_density=DEFAULT_HUMANIZE_DENSITY,
            humanize_seed=None,
            reformat=True,
            concurrency=DEFAULT_CONCURRENCY,
        )
    except MissingAPIKeyError as e:
        log.error("assignment failed: missing API key")
        raise HTTPException(500, str(e))
    except Exception as e:
        log.exception("assignment failed: PDF generation crashed")
        raise HTTPException(500, f"PDF generation failed: {e}")

    if not os.path.isfile(written_path) or os.path.getsize(written_path) == 0:
        log.error("assignment failed: produced empty PDF at %s", written_path)
        raise HTTPException(500, "PDF generation produced no output.")

    log.info("assignment delivered  %s (%d bytes)", written_path, os.path.getsize(written_path))
    return FileResponse(
        written_path,
        media_type="application/pdf",
        filename="assignment.pdf",
    )


# --- JSON API ---------------------------------------------------------------


@app.post("/api/humanize")
async def api_humanize(req: HumanizeRequest):
    if req.density not in DENSITIES:
        raise HTTPException(400, f"invalid density (allowed: {list(DENSITIES)})")
    result = humanize_pipeline(req.text, density=req.density, seed=req.seed)
    return {
        "result": result,
        "input_chars": len(req.text),
        "output_chars": len(result),
        "output_words": len(result.split()),
    }


@app.post("/api/assignment")
async def api_assignment(req: QaPdfRequest):
    try:
        specs = _parse_questions_payload([q.model_dump() for q in req.questions])
    except ValueError as e:
        raise HTTPException(400, str(e))

    if req.humanize_density not in DENSITIES:
        raise HTTPException(400, "invalid humanize_density")

    out_dir = tempfile.mkdtemp(prefix="answers-")
    stub_path = os.path.join(out_dir, "answers.pdf")

    try:
        written_path = await asyncio.to_thread(
            _run_qa_pdf_sync,
            specs,
            out_path=stub_path,
            title=req.title,
            model=req.model,
            temperature=req.temperature,
            humanize_density=req.humanize_density,
            humanize_seed=req.humanize_seed,
            reformat=req.reformat,
            concurrency=req.concurrency,
        )
    except MissingAPIKeyError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        raise HTTPException(500, f"PDF generation failed: {e}")

    if not os.path.isfile(written_path) or os.path.getsize(written_path) == 0:
        raise HTTPException(500, "PDF generation produced no output.")

    return FileResponse(
        written_path,
        media_type="application/pdf",
        filename="answers.pdf",
    )


@app.get("/api/health")
async def health():
    return JSONResponse(
        {"ok": True, "has_openai_key": bool(os.environ.get("OPENAI_API_KEY"))}
    )
