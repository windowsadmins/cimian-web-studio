"""Cimian catalogs: how they are named and read, and the checks a generated set
must pass before it replaces the repository's catalogs.

Cimian's makecatalogs reads each pkginfo into a typed model (YamlDotNet), keeps
only the fields that model declares, fills in its defaults, stamps each item with
`loop_fingerprint`, and writes `catalogs/<name>.yaml` as `items:` followed by the
items. The studio rebuilds every item the same way from its own reading of the
pkginfo and requires the generated files to match it exactly, byte for byte.
"""

import hashlib
import re
from collections.abc import Iterator
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, cast

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from ruamel.yaml.events import (
    AliasEvent,
    CollectionStartEvent,
    DocumentEndEvent,
    DocumentStartEvent,
    Event,
    MappingEndEvent,
    MappingStartEvent,
    NodeEvent,
    ScalarEvent,
    SequenceEndEvent,
    SequenceStartEvent,
    StreamEndEvent,
    StreamStartEvent,
)
from ruamel.yaml.tag import Tag

FOLDER = "catalogs"
SUFFIX = ".yaml"
# makecatalogs always writes this catalog, holding every pkginfo.
ALL = "All"


class CatalogError(ValueError):
    pass


def name_of(path: str) -> str:
    """The catalog a file holds: `catalogs/testing.yaml` holds `testing`."""
    file = path.rsplit("/", 1)[-1]
    return file.removesuffix(SUFFIX)


def file_for(name: str) -> str:
    return f"{FOLDER}/{name}{SUFFIX}"


# The model makecatalogs reads a pkginfo into (Cimian.CLI.Makecatalogs.Models),
# in the order it writes the fields. A field is a scalar type, a list of one,
# a nested model, or a list of nested models.
STR, BOOL, INT, DATE = "str", "bool", "int", "datetime"
Model = tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class ListOf:
    kind: Any


INSTALLER: Model = (
    ("location", STR),
    ("hash", STR),
    ("type", STR),
    ("size", INT),
    ("switches", ListOf(STR)),
    ("flags", ListOf(STR)),
    ("success_codes", ListOf(INT)),
    ("subcommand", STR),
    ("arguments", ListOf(STR)),
    ("args", ListOf(STR)),
    ("temp_dir", STR),
    ("product_code", STR),
    ("upgrade_code", STR),
    ("identity_name", STR),
)
INSTALL_ITEM: Model = tuple(
    (k, STR)
    for k in (
        "type",
        "path",
        "md5checksum",
        "version",
        "product_code",
        "upgrade_code",
        "display_name",
        "identity_name",
    )
)
REMOVAL_INFO: Model = (
    ("removal_days", INT),
    ("paths", ListOf(STR)),
    ("minimum_history_days", INT),
)
INSTALL_WINDOW: Model = (("start", STR), ("end", STR), ("weekdays", ListOf(STR)))
CHECK: Model = (
    ("registry", tuple((k, STR) for k in ("name", "version", "path", "value"))),
    ("file", tuple((k, STR) for k in ("path", "version", "hash"))),
    ("script", STR),
)
ITEM: Model = (
    ("name", STR),
    ("display_name", STR),
    ("identifier", STR),
    ("version", STR),
    ("description", STR),
    ("catalogs", ListOf(STR)),
    ("category", STR),
    ("developer", STR),
    ("icon_name", STR),
    ("requires", ListOf(STR)),
    ("update_for", ListOf(STR)),
    ("installs", ListOf(INSTALL_ITEM)),
    ("blocking_applications", ListOf(STR)),
    ("supported_architectures", ListOf(STR)),
    ("unattended_install", BOOL),
    ("unattended_uninstall", BOOL),
    ("unused_software_removal_info", REMOVAL_INFO),
    ("minimum_os_version", STR),
    ("maximum_os_version", STR),
    ("minimum_cimian_version", STR),
    ("installer", INSTALLER),
    ("uninstaller", ListOf(INSTALLER)),
    ("preinstall_script", STR),
    ("postinstall_script", STR),
    ("preuninstall_script", STR),
    ("postuninstall_script", STR),
    ("installcheck_script", STR),
    ("uninstallcheck_script", STR),
    ("uninstallable", BOOL),
    ("install_script", STR),
    ("uninstall_script", STR),
    ("version_script", STR),
    ("restart_action", STR),
    ("installer_timeout", INT),
    ("force_install_after_date", DATE),
    ("precache", BOOL),
    ("check", CHECK),
    ("install_window", INSTALL_WINDOW),
    ("OnDemand", BOOL),
    ("recurring", BOOL),
    ("loop_fingerprint", STR),
)

# What makecatalogs changes between a pkginfo and its catalog entry. Every key
# outside the model is dropped, at any depth. These are added when a pkginfo
# leaves them out: non-nullable fields of the model, written with their defaults,
# and the fingerprint, which is always recomputed.
KEPT_KEYS = frozenset(k for k, _ in ITEM)
ADDED_KEYS: dict[str, type] = {
    "unattended_install": bool,
    "unattended_uninstall": bool,
    "OnDemand": bool,
    "recurring": bool,
    "loop_fingerprint": str,
}
_DEFAULTS: dict[Model, dict[str, Any]] = {
    ITEM: {
        "unattended_install": False,
        "unattended_uninstall": False,
        "OnDemand": False,
        "recurring": False,
    },
}
# Top-level text fields whose blank lines makecatalogs keeps; in every other
# top-level text field it collapses three or more line breaks to two.
_SCRIPTS = frozenset(k for k, _ in ITEM if k.endswith("_script"))
_NULLS = frozenset({"", "~", "null", "Null", "NULL"})
_INTEGER = re.compile(r"-?(0|[1-9][0-9]*)")


def dropped_keys(source: dict[str, Any]) -> set[str]:
    """The top-level keys of a pkginfo that makecatalogs leaves out of its entry."""
    return set(source) - KEPT_KEYS


def key(item: dict[str, Any]) -> tuple[str, str]:
    return str(item.get("name", "")), str(item.get("version", ""))


def same(a: Any, b: Any) -> bool:
    """Equal values of the same types all the way down, so True never stands in
    for 1 or 1.0 for 1."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        x, y = cast(dict[Any, Any], a), cast(dict[Any, Any], b)
        return x.keys() == y.keys() and all(same(x[k], y[k]) for k in x)
    if isinstance(a, list):
        x, y = cast(list[Any], a), cast(list[Any], b)
        return len(x) == len(y) and all(same(i, j) for i, j in zip(x, y, strict=True))
    return bool(a == b)


# Reading a pkginfo the way makecatalogs does.


def _unpredictable(path: str, value: Any) -> CatalogError:
    return CatalogError(f"{path}: cannot tell how makecatalogs reads {value!r}")


def _expect(value: Any, kind: Any, path: str) -> Any:
    """A pkginfo value as the model holds it, or None when the field is left out."""
    if value is None:
        return None
    if isinstance(kind, ListOf):
        if not isinstance(value, list):
            raise _unpredictable(path, value)
        items: list[Any] = []
        for i, entry in enumerate(cast(list[Any], value)):
            # An empty string is left out as a field but kept as a list entry.
            empty = entry == "" and kind.kind == STR
            item = "" if empty else _expect(entry, kind.kind, f"{path}[{i}]")
            if item is None:
                raise _unpredictable(f"{path}[{i}]", entry)
            items.append(item)
        return items or None
    if isinstance(kind, tuple):
        if not isinstance(value, dict):
            raise _unpredictable(path, value)
        return _project(cast(dict[str, Any], value), cast(Model, kind), path)
    if kind == BOOL:
        if not isinstance(value, bool):
            raise _unpredictable(path, value)
        return value
    if kind == INT:
        if isinstance(value, bool) or not isinstance(value, int):
            raise _unpredictable(path, value)
        return value
    if kind == STR:
        if isinstance(value, str):
            # YamlDotNet counts a string as a collection, so an empty one is
            # left out like an empty list.
            return value or None
        # YamlDotNet reads the scalar's text. The codec has already turned an
        # unquoted 5 into 5 and 5.0 into 5.0, whose text Python reproduces;
        # where it does not (2.10), the comparison fails and nothing is replaced.
        if isinstance(value, int | float) and not isinstance(value, bool):
            return str(value)
        raise _unpredictable(path, value)
    raise _unpredictable(path, value)


def _project(source: dict[str, Any], model: Model, path: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    defaults = _DEFAULTS.get(model, {})
    for field, kind in model:
        value = _expect(source.get(field), kind, f"{path}.{field}" if path else field)
        if value is None:
            value = defaults.get(field)
        if value is not None:
            result[field] = value
    return result


def _normalize(item: dict[str, Any]) -> None:
    """The line-ending clean-up makecatalogs applies to top-level text fields."""
    for field, value in item.items():
        if not isinstance(value, str) or ("\r" not in value and "\n\n\n" not in value):
            continue
        text = value.replace("\r\n", "\n").replace("\r", "\n")
        while field not in _SCRIPTS and "\n\n\n" in text:
            text = text.replace("\n\n\n", "\n\n")
        item[field] = text


def expected_item(source: dict[str, Any]) -> dict[str, Any]:
    """The catalog entry makecatalogs writes for a pkginfo."""
    if DATE in (kind for field, kind in ITEM if source.get(field) is not None):
        raise CatalogError("force_install_after_date cannot be checked yet")
    item = _project({k: v for k, v in source.items() if k != "loop_fingerprint"}, ITEM)
    _normalize(item)
    item["loop_fingerprint"] = fingerprint(item)
    return {field: item[field] for field, _ in ITEM if field in item}


# Writing YAML the way YamlDotNet does. Its emitter and ruamel's are both ports
# of libyaml, so they choose the same scalar styles; the settings below match
# Cimian's serializer (indented sequences, no line folding, `|` for any text
# with a line break).


_STR = Tag(suffix="tag:yaml.org,2002:str")


def _scalar(value: Any) -> ScalarEvent:
    if isinstance(value, bool):
        return ScalarEvent(None, None, (True, False), "true" if value else "false")
    if isinstance(value, int):
        return ScalarEvent(None, None, (True, False), str(value))
    text = cast(str, value)
    # YamlDotNet writes an empty string as ''; ruamel would leave it bare.
    style = "'" if not text else "|" if "\n" in text else None
    return ScalarEvent(None, _STR, (True, True), text, style=style)


def _value_events(value: Any) -> Iterator[Event]:
    if isinstance(value, dict):
        # An object with every field left out is written as `{}`.
        yield MappingStartEvent(None, None, True, flow_style=not value)
        for k, v in cast(dict[str, Any], value).items():
            yield _scalar(k)
            yield from _value_events(v)
        yield MappingEndEvent()
    elif isinstance(value, list):
        yield SequenceStartEvent(None, None, True, flow_style=False)
        for v in cast(list[Any], value):
            yield from _value_events(v)
        yield SequenceEndEvent()
    else:
        yield _scalar(value)


def _emit(root: Any, *, indented: bool, newline: str) -> str:
    yaml = YAML(typ="safe", pure=True)
    yaml.width = 1 << 30
    yaml.allow_unicode = True
    yaml.line_break = newline  # pyright: ignore[reportAttributeAccessIssue]
    if indented:
        yaml.indent(mapping=2, sequence=4, offset=2)
    else:
        yaml.indent(mapping=2, sequence=2, offset=0)
    events: list[Event] = [StreamStartEvent(), DocumentStartEvent(explicit=False)]
    events += _value_events(root)
    events += [DocumentEndEvent(explicit=False), StreamEndEvent()]
    out = StringIO()
    yaml.emit(events, out)
    return out.getvalue()


def render(items: list[dict[str, Any]], newline: str = "\r\n") -> bytes:
    """A catalog file as makecatalogs writes it. On Windows lines end in CRLF."""
    root: dict[str, Any] = {"items": items} if items else {}
    return _emit(root, indented=True, newline=newline).encode("utf-8")


def fingerprint(item: dict[str, Any]) -> str:
    """makecatalogs' loop_fingerprint: the first 16 hex digits of the SHA-256 of
    the item written as a pkginfo (name, display_name and version first, then the
    other keys in ordinal order, empty top-level strings left out, sequences not
    indented, LF line endings), without its own fingerprint."""
    first = [k for k in ("name", "display_name", "version") if k in item]
    rest = sorted(k for k in item if k not in first and k != "loop_fingerprint")
    ordered = {k: item[k] for k in [*first, *rest] if item[k] != ""}
    text = _emit(ordered, indented=False, newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# Reading a catalog strictly.


@dataclass(frozen=True)
class _Scalar:
    text: str
    plain: bool


def _tree(raw: bytes) -> Any:
    """One YAML document of mappings, sequences and scalars: no anchors,
    aliases, tags, duplicate keys or document markers, any of which a client
    might read differently from the studio. Flow style is left to the byte
    comparison in `canonical`, which allows it only for an empty `{}`."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CatalogError(f"not UTF-8: {error.reason}") from None
    try:
        parser = cast(Any, YAML(typ="safe", pure=True))
        events = cast(list[Event], list(parser.parse(text)))
    except YAMLError as error:
        raise CatalogError(f"not YAML: {error}") from None
    stack: list[Any] = []
    keys: list[Any] = []
    root: Any = None
    documents = 0
    for event in events:
        # ruamel's events carry their fields untyped.
        fields = cast(Any, event)
        if isinstance(event, AliasEvent):
            raise CatalogError("aliases are not allowed")
        if isinstance(event, NodeEvent) and fields.anchor is not None:
            raise CatalogError("anchors are not allowed")
        if isinstance(event, ScalarEvent | CollectionStartEvent) and fields.tag is not None:
            raise CatalogError("tags are not allowed")
        if isinstance(event, DocumentStartEvent):
            documents += 1
            if documents > 1 or fields.explicit:
                raise CatalogError("a catalog must be one implicit document")
            continue
        if isinstance(event, DocumentEndEvent) and fields.explicit:
            raise CatalogError("a catalog must be one implicit document")
        node: Any
        if isinstance(event, ScalarEvent):
            node = _Scalar(str(fields.value), not fields.style)
        elif isinstance(event, MappingStartEvent):
            stack.append({})
            keys.append(None)
            continue
        elif isinstance(event, SequenceStartEvent):
            stack.append([])
            keys.append(None)
            continue
        elif isinstance(event, MappingEndEvent | SequenceEndEvent):
            node = stack.pop()
            keys.pop()
        else:
            continue
        if not stack:
            root = node
            continue
        parent = stack[-1]
        if isinstance(parent, list):
            cast(list[Any], parent).append(node)
        elif keys[-1] is None:
            if not isinstance(node, _Scalar) or not node.plain:
                raise CatalogError("keys must be plain text")
            if node.text in parent:
                raise CatalogError(f"duplicate key {node.text!r}")
            keys[-1] = node.text
        else:
            cast(dict[str, Any], parent)[keys[-1]] = node
            keys[-1] = None
    return root


def _read(node: Any, kind: Any, path: str) -> Any:
    if isinstance(kind, ListOf):
        if not isinstance(node, list):
            raise CatalogError(f"{path} must be a list")
        return [_read(n, kind.kind, f"{path}[{i}]") for i, n in enumerate(cast(list[Any], node))]
    if isinstance(kind, tuple):
        if not isinstance(node, dict):
            raise CatalogError(f"{path} must be a mapping")
        mapping = cast(dict[str, Any], node)
        model = dict(cast(Model, kind))
        unknown = sorted(set(mapping) - set(model))
        if unknown:
            raise CatalogError(f"{path} has keys makecatalogs does not write: {unknown}")
        return {k: _read(v, model[k], f"{path}.{k}") for k, v in mapping.items()}
    if not isinstance(node, _Scalar):
        raise CatalogError(f"{path} must be a single value")
    if kind == BOOL:
        if not node.plain or node.text not in ("true", "false"):
            raise CatalogError(f"{path} must be true or false")
        return node.text == "true"
    if kind == INT:
        if not node.plain or not _INTEGER.fullmatch(node.text):
            raise CatalogError(f"{path} must be a whole number")
        return int(node.text)
    if kind == STR:
        if node.plain and node.text in _NULLS:
            raise CatalogError(f"{path} reads as null")
        return node.text
    raise CatalogError(f"{path} cannot be checked")


def entries(raw: bytes) -> list[dict[str, Any]]:
    """A catalog's items, each read into makecatalogs' model."""
    root = _tree(raw)
    if not isinstance(root, dict):
        raise CatalogError("A catalog must be a mapping holding items")
    mapping = cast(dict[str, Any], root)
    if set(mapping) - {"items"}:
        raise CatalogError("A catalog holds only items")
    items = mapping.get("items", [])
    if not isinstance(items, list):
        raise CatalogError("items must be a list")
    return [_read(i, ITEM, f"items[{n}]") for n, i in enumerate(cast(list[Any], items))]


def canonical(raw: bytes) -> list[dict[str, Any]]:
    """A generated catalog's items, but only if the file is exactly what
    makecatalogs writes for them: the strict reading above, then the items
    written back out the way YamlDotNet writes them must give the same bytes.
    That refuses comments, other quoting, key order or indentation, and anything
    else a client might read differently. Either line ending is accepted, as long
    as every line uses it."""
    items = entries(raw)
    newline = "\r\n" if b"\r\n" in raw else "\n"
    if render(items, newline) != raw:
        raise CatalogError("not in the form makecatalogs writes")
    return items


def check_output(folder: Path, sources: list[dict[str, Any]]) -> dict[str, int]:
    """Refuse generated catalogs that are not exactly what the pkginfo say.

    The worker is trusted to run makecatalogs, not to decide what clients
    install, so every entry is compared with the item the studio builds from its
    own reading of the pkginfo, fingerprint included. Each catalog must hold
    exactly the pkginfo that list it, and no catalog may appear that no pkginfo
    names. Catalog names match without regard to case, as in makecatalogs, and
    the first spelling seen names the file. Returns each catalog's item count."""
    expected: dict[str, list[dict[str, Any]]] = {ALL: []}
    spelling: dict[str, str] = {ALL.lower(): ALL}
    for source in sources:
        item = expected_item(source)
        expected[ALL].append(item)
        for listed in cast(list[str], item.get("catalogs", [])):
            if not listed.strip():
                continue
            name = spelling.setdefault(listed.lower(), listed)
            expected.setdefault(name, []).append(item)
    counts: dict[str, int] = {}
    for path in sorted(folder.iterdir()) if folder.is_dir() else []:
        if path.name.startswith("."):
            continue
        if path.is_symlink() or not path.is_file() or not path.name.endswith(SUFFIX):
            raise CatalogError(f"{path.name} is not a catalog file")
        name = name_of(path.name)
        if name not in expected:
            raise CatalogError(f"{path.name} is not a catalog any pkginfo names")
        try:
            items = canonical(path.read_bytes())
        except CatalogError as error:
            raise CatalogError(f"{path.name} cannot be read: {error}") from None
        remaining = list(expected[name])
        for item in items:
            match = next((i for i, want in enumerate(remaining) if same(want, item)), None)
            if match is None:
                label = " ".join(key(item)).strip() or "an item"
                raise CatalogError(f"{path.name}: {label} does not match any pkginfo")
            remaining.pop(match)
        if remaining:
            missing = ", ".join(sorted({" ".join(key(i)) for i in remaining}))
            raise CatalogError(f"{path.name} is missing {missing}")
        counts[name] = len(items)
    absent = sorted(set(expected) - set(counts))
    if absent:
        raise CatalogError(f"No catalog was generated for {', '.join(absent)}")
    return counts
