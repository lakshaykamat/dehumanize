"""Constants and defaults for the qa pipeline."""

DEFAULT_MODEL = "gpt-5.2"
DEFAULT_TEMPERATURE = 0.3
DEFAULT_TITLE = "Questions & Answers"

# Retry budget per question when the answer falls outside the word range.
MAX_RETRIES = 3

# Humanize step (always runs; only the density is configurable)
DEFAULT_HUMANIZE_DENSITY = "high"

# Initial guess for humanize inflation factor (final_words / raw_words).
# Refined per-question after the first attempt.
INFLATION_GUESS = {"low": 1.05, "med": 1.15, "high": 1.30}

# Max in-flight OpenAI requests when generating in parallel. Bounded to stay
# inside typical per-minute tier limits; each question may fire up to
# MAX_RETRIES+1 calls, so the effective burst can be higher.
DEFAULT_CONCURRENCY = 10
