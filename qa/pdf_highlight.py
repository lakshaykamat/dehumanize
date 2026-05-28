"""Pygments-based syntax highlighter that emits ReportLab paragraph markup.

The output of :func:`highlight_code` is a string of escaped source text with
inline ``<font color="#xxxxxx">`` spans — safe to drop into an
``XPreformatted`` flowable, which preserves whitespace and accepts the same
inline tags as ``Paragraph``.

Why not use Pygments' built-in HTML formatter? It emits CSS class names that
ReportLab doesn't resolve, plus ``<span>`` tags ReportLab ignores. We need
inline color attributes.
"""

from __future__ import annotations

import re
from html import escape

from pygments import lex
from pygments.lexers import TextLexer, get_lexer_by_name, guess_lexer
from pygments.token import Token
from pygments.util import ClassNotFound


# Token → hex color. Tuned for a dark slate background (#1f2937) so the
# palette stays readable and the warm/cool contrast tracks GitHub-dark / VS Code.
_PALETTE: dict = {
    Token.Keyword:                 "#f59e0b",   # amber  — class, def, return, import
    Token.Keyword.Constant:        "#f59e0b",
    Token.Keyword.Declaration:     "#f59e0b",
    Token.Keyword.Namespace:       "#f59e0b",
    Token.Keyword.Pseudo:          "#f59e0b",
    Token.Keyword.Reserved:        "#f59e0b",
    Token.Keyword.Type:            "#fbbf24",
    Token.Name.Class:              "#fde68a",   # light amber — type names
    Token.Name.Function:           "#fde68a",
    Token.Name.Decorator:          "#fbbf24",
    Token.Name.Builtin:            "#fbbf24",
    Token.Name.Builtin.Pseudo:     "#fbbf24",
    Token.Name.Exception:          "#fda4af",
    Token.Literal.String:          "#86efac",   # green
    Token.Literal.String.Doc:      "#86efac",
    Token.Literal.String.Escape:   "#a7f3d0",
    Token.Literal.Number:          "#67e8f9",   # cyan
    Token.Literal:                 "#86efac",
    Token.Comment:                 "#94a3b8",   # muted slate
    Token.Comment.Single:          "#94a3b8",
    Token.Comment.Multiline:       "#94a3b8",
    Token.Operator:                "#f1f5f9",
    Token.Operator.Word:           "#f59e0b",
    Token.Punctuation:             "#cbd5e1",
}


def _color_for(token_type) -> str | None:
    """Walk up the token hierarchy until we find a palette entry."""
    t = token_type
    while t is not None:
        if t in _PALETTE:
            return _PALETTE[t]
        t = t.parent
    return None


def _pick_lexer(language: str, source: str):
    """Return a lexer for the given language hint, falling back to guessing
    then to plain text — never raises."""
    if language:
        try:
            return get_lexer_by_name(language, stripall=False)
        except ClassNotFound:
            pass
    try:
        return guess_lexer(source)
    except ClassNotFound:
        return TextLexer()


# ---------------------------------------------------------------------------
# Inline (single-line) highlighter
# ---------------------------------------------------------------------------
#
# Pygments' `guess_lexer` is unreliable on the very short snippets that appear
# inside `backticks`, so we tokenize with a single regex and detect the
# language by keyword overlap (SQL vs Python vs neither). This gives:
#   * function-call identifiers in salmon (e.g. `StudentPhone(SID, Phone)`)
#   * strings green, numbers cyan
#   * SQL/Python keywords amber only when the snippet looks like that language
#   * everything else in the default code color (no false positives on prose)

_INLINE_TOKEN_RE = re.compile(
    r"""
    (?P<string>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")
    | (?P<number>\b\d+(?:\.\d+)?\b)
    | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
    | (?P<other>\s+|.)
    """,
    re.VERBOSE,
)

_SQL_KEYWORDS = frozenset({
    "select", "from", "where", "and", "or", "not", "insert", "into", "values",
    "update", "set", "delete", "join", "inner", "left", "right", "outer", "on",
    "group", "by", "order", "having", "union", "distinct", "limit", "offset",
    "null", "true", "false", "case", "when", "then", "else", "end", "exists",
    "like", "between", "primary", "key", "foreign", "references", "table",
    "create", "drop", "alter", "constraint", "unique", "index", "view",
})

_PY_KEYWORDS = frozenset({
    "def", "return", "class", "if", "elif", "else", "for", "while", "import",
    "from", "as", "try", "except", "finally", "raise", "with", "lambda",
    "yield", "pass", "break", "continue", "global", "nonlocal", "is", "not",
    "and", "or", "in", "True", "False", "None", "async", "await",
})

# Words that are SQL keywords but appear so commonly in plain English that
# coloring them as keywords misfires more often than it helps. Only color
# these when the snippet clearly is SQL (multiple distinct SQL keywords).
_SQL_AMBIGUOUS = frozenset({"as", "is", "in", "by", "on", "or", "and", "not"})


def _detect_inline_lang(idents: list[str]) -> str:
    """Return "sql", "python", or "" based on keyword overlap. Conservative:
    requires at least one unambiguous keyword to declare a language so that
    pseudo-relational prose like ``Student(SID, as observed Phones)`` does
    not light up its ``as`` / ``in`` words."""
    lowered = {t.lower() for t in idents}
    sql_strong = (lowered & _SQL_KEYWORDS) - _SQL_AMBIGUOUS
    py_strong = {t for t in idents if t in _PY_KEYWORDS} - {"is", "in", "as", "not", "and", "or"}
    if len(sql_strong) > len(py_strong) and sql_strong:
        return "sql"
    if py_strong:
        return "python"
    return ""


def highlight_inline(
    snippet: str,
    *,
    default_color: str,
    function_color: str,
    keyword_color: str = "#f59e0b",
    string_color: str = "#86efac",
    number_color: str = "#67e8f9",
) -> str:
    """Render a `backtick` snippet as escaped reportlab markup. Always
    highlights function-call identifiers; only highlights language keywords
    when the snippet looks like that language."""
    tokens = list(_INLINE_TOKEN_RE.finditer(snippet))
    idents = [m.group("ident") for m in tokens if m.lastgroup == "ident"]
    lang = _detect_inline_lang(idents)

    parts: list[str] = []
    for i, m in enumerate(tokens):
        kind = m.lastgroup
        val = m.group()
        if kind == "string":
            parts.append(f'<font color="{string_color}">{escape(val)}</font>')
        elif kind == "number":
            parts.append(f'<font color="{number_color}">{escape(val)}</font>')
        elif kind == "ident":
            # Lookahead past whitespace for "(" → function-call identifier.
            j = i + 1
            while j < len(tokens) and tokens[j].lastgroup == "other" and tokens[j].group().isspace():
                j += 1
            is_fn = j < len(tokens) and tokens[j].group() == "("
            lo = val.lower()
            if is_fn:
                parts.append(f'<font color="{function_color}">{escape(val)}</font>')
            elif lang == "sql" and lo in _SQL_KEYWORDS:
                parts.append(f'<font color="{keyword_color}">{escape(val)}</font>')
            elif lang == "python" and val in _PY_KEYWORDS:
                parts.append(f'<font color="{keyword_color}">{escape(val)}</font>')
            else:
                parts.append(escape(val))
        else:
            parts.append(escape(val))
    return "".join(parts)


def highlight_code(source: str, language: str, default_color: str) -> str:
    """Return the source as escaped reportlab paragraph markup with inline
    ``<font color="...">`` spans per Pygments token.

    `default_color` is applied to any text whose token type has no palette
    entry, ensuring all glyphs render (no invisible-on-dark text).
    """
    lexer = _pick_lexer(language, source)
    parts: list[str] = []
    for ttype, value in lex(source, lexer):
        if not value:
            continue
        color = _color_for(ttype) or default_color
        # XPreformatted preserves \n exactly, but inline markup is per-line —
        # split tokens that contain newlines so each colored span stays on one line.
        for i, segment in enumerate(value.split("\n")):
            if i > 0:
                parts.append("\n")
            if not segment:
                continue
            parts.append(f'<font color="{color}">{escape(segment)}</font>')
    return "".join(parts)
