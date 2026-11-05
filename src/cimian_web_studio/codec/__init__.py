"""Read and edit Cimian repository files without disturbing what was not changed.

`load` detects the format and returns a `Document` holding the original bytes
and their typed reading. `edit` applies changes by replacing only the affected
bytes where it can, falls back to a whole-file rewrite where it cannot, and
re-reads the result to prove it holds exactly the intended data.
"""

import contextlib
from typing import Any

from cimian_web_studio.codec import yamlfile
from cimian_web_studio.codec.model import (
    MAX_FILE_BYTES,
    Append,
    Change,
    CodecError,
    Delete,
    Document,
    EditResult,
    Format,
    ParseError,
    Set,
    apply_to_data,
    check_bounds,
    first_difference,
    revision_of,
)

__all__ = [
    "Append",
    "Change",
    "CodecError",
    "Delete",
    "Document",
    "EditResult",
    "Format",
    "ParseError",
    "Set",
    "detect_format",
    "edit",
    "load",
    "revision_of",
]


# Fields Cimian reads as text, whatever they look like. Cimian's own reader binds
# these to string properties, so `version: 2.10` means "2.10" and a hash of
# zeros is a string. The typed reading must agree.
TEXT_KEYS = frozenset(
    {
        "name",
        "display_name",
        "version",
        "hash",
        "product_code",
        "upgrade_code",
        "minimum_os_version",
        "maximum_os_version",
        "location",
        "path",
        "developer",
        "category",
        "description",
        "identifier",
    }
)


def detect_format(raw: bytes) -> Format:
    """Cimian metadata is always YAML."""
    del raw
    return Format.YAML


def _parse(raw: bytes, fmt: Format) -> Any:
    del fmt
    try:
        data = yamlfile.load(raw, TEXT_KEYS)
    except RecursionError as error:
        raise ParseError("Nesting is too deep to read") from error
    check_bounds(data)
    return data


def load(raw: bytes) -> Document:
    if len(raw) > MAX_FILE_BYTES:
        raise ParseError(f"File is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB")
    fmt = detect_format(raw)
    return Document(raw=raw, format=fmt, data=_parse(raw, fmt))


def edit(document: Document, changes: list[Change]) -> EditResult:
    """Return new bytes for the document with the changes applied."""
    expected = apply_to_data(document.data, changes)
    if not changes or first_difference(expected, document.data) is None:
        return EditResult(raw=document.raw, surgical=True)

    candidates: list[tuple[bytes, bool]] = []
    with contextlib.suppress(CodecError, KeyError, IndexError, ValueError):
        candidates.append((yamlfile.edit(document.raw, changes), True))
    candidates.append((yamlfile.rewrite(document.raw, changes), False))

    problems: list[str] = []
    for raw, surgical in candidates:
        try:
            actual = _parse(raw, document.format)
        except ParseError as error:
            problems.append(str(error))
            continue
        difference = first_difference(expected, actual)
        if difference is None:
            return EditResult(raw=raw, surgical=surgical)
        problems.append(difference)
    raise CodecError("Edit could not be verified: " + "; ".join(problems))
