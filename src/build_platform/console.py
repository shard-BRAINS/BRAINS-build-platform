"""Console-safe output.

Files written under `.brains-build/` are UTF-8 and stay typeset — em-dashes,
middle dots, arrows and all. A Windows console is often cp1252, which cannot
encode any of them: printing one raises `UnicodeEncodeError` and kills the
command. Reconfiguring the stream with `errors="replace"` avoids the crash but
prints `?` where the punctuation was, which is worse than plain ASCII.

So: degrade deliberately. When the stream can encode the text, it goes out
verbatim. When it cannot, typography is transliterated to an ASCII equivalent
that still reads correctly. Only the terminal copy degrades; the file on disk
is untouched.
"""
import sys

import click

# Deliberate, readable ASCII stand-ins. Anything not listed here falls through
# to the encode(errors="replace") backstop below.
_TRANSLITERATIONS = {
    "—": "--",   # em dash
    "–": "-",    # en dash
    "·": "*",    # middle dot (used as a field separator)
    "•": "*",    # bullet
    "→": "->",   # rightwards arrow
    "≤": "<=",
    "≥": ">=",
    "≠": "!=",
    "…": "...",  # ellipsis
    "‘": "'",    # curly quotes
    "’": "'",
    "“": '"',
    "”": '"',
    "✓": "OK",   # check mark
    "✗": "X",    # ballot X
    " ": " ",    # non-breaking space
    "€": "EUR",
    "£": "GBP",
}

_TRANSLATION_TABLE = str.maketrans(_TRANSLITERATIONS)


def _encoding_of(stream) -> str:
    """Best-effort encoding for a stream. Assume UTF-8 when it won't say."""
    return getattr(stream, "encoding", None) or "utf-8"


def console_safe(text: str, stream=None) -> str:
    """Return `text` rendered so `stream` can encode every character.

    Returns the text unchanged when the stream handles it — which is the case
    for UTF-8 terminals, redirected output, and pytest's captured streams, so
    typeset output is preserved everywhere it actually works.
    """
    if not isinstance(text, str):
        return text
    encoding = _encoding_of(stream if stream is not None else sys.stdout)
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        pass
    else:
        return text

    out = text.translate(_TRANSLATION_TABLE)
    try:
        out.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        # Backstop for anything not in the table: drop to ASCII rather than
        # emit replacement characters.
        out = out.encode("ascii", "replace").decode("ascii")
    return out


def echo(message: str = "", *, err: bool = False, **kwargs) -> None:
    """`click.echo`, with the message made safe for the destination stream."""
    stream = sys.stderr if err else sys.stdout
    click.echo(console_safe(message, stream), err=err, **kwargs)
