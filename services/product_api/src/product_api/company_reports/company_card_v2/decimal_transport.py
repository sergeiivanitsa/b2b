from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re

_DECIMAL = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?$")


class DecimalTransportError(ValueError):
    """The source representation is not a lossless Decimal lexeme."""


class SourceDecimal:
    """A canonical source Decimal with its verified transport lexeme.

    Floats are intentionally not accepted: a float no longer represents the
    provider's lexical value and therefore cannot be used as financial truth.
    """

    __slots__ = ("value", "lexeme")

    def __init__(self, value: Decimal, lexeme: str) -> None:
        self.value = value
        self.lexeme = lexeme

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SourceDecimal) and (self.value, self.lexeme) == (other.value, other.lexeme)

    def __repr__(self) -> str:
        return f"SourceDecimal({self.lexeme!r})"


def parse_source_decimal(value: object) -> SourceDecimal:
    """Parse only the approved JSON numeric/string lexical grammar.

    The caller must pass a string only when it is an exact JSON number lexeme
    obtained from the response-byte manifest. Plain JSON numbers decoded by
    Python are accepted only as ``Decimal``; ints/floats/bools are rejected.
    """
    if isinstance(value, Decimal):
        lexeme = format(value, "f")
    elif isinstance(value, str):
        lexeme = value
    else:
        raise DecimalTransportError("source decimal must be an exact string or Decimal")
    if not lexeme.isascii() or len(lexeme.encode("ascii")) > 128 or not _DECIMAL.fullmatch(lexeme):
        raise DecimalTransportError("source decimal lexeme is invalid")
    digits = [ch for ch in lexeme if ch.isdigit()]
    if len(digits) > 96:
        raise DecimalTransportError("source decimal has too many significant digits")
    if "." in lexeme and len(lexeme.rsplit(".", 1)[1]) > 32:
        raise DecimalTransportError("source decimal has too many fractional digits")
    try:
        decimal = Decimal(lexeme)
    except InvalidOperation as exc:  # defensive: regex should have excluded it
        raise DecimalTransportError("source decimal is invalid") from exc
    if decimal.is_zero():
        canonical = "0"
        decimal = Decimal("0")
    elif "." in lexeme:
        canonical = lexeme.rstrip("0").rstrip(".")
    else:
        canonical = lexeme
    return SourceDecimal(decimal, canonical)


def json_pointer_escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


__all__ = ["DecimalTransportError", "SourceDecimal", "json_pointer_escape", "parse_source_decimal"]
