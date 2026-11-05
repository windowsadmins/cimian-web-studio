"""Cimian conditions: parse the predicate strings Cimian manifests use, for
display and validation. Nothing here evaluates a condition against a machine.

    analyze("hostname CONTAINS Design- AND arch == x64")
    -> rule: "hostname contains 'Design-' and architecture is 'x64'"

Follows Cimian's predicate engine: bare words after an operator are values,
operators have word forms (EQUALS, DOES_NOT_CONTAIN, ...), and ANY allows
only ==, != and CONTAINS. Unknown facts are allowed (custom facts, environment
variables and registry values are looked up by name) and reported as warnings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Facts Cimian gathers itself (shared/core/Models/SystemFacts.cs).
KNOWN_FACTS: dict[str, str] = {
    "hostname": "hostname",
    "arch": "architecture",
    "architecture": "architecture",
    "os_version": "Windows version",
    "os_vers_major": "Windows major version",
    "os_vers_minor": "Windows minor version",
    "os_build_number": "Windows build",
    "domain": "domain",
    "username": "user name",
    "machine_type": "machine type",
    "machine_model": "computer model",
    "model_version": "model name",
    "joined_type": "join type",
    "catalogs": "catalogs",
    "battery_state": "battery state",
    "date": "date",
    "gpu_names": "GPU names",
    "gpu_name": "GPU name",
    "gpu_driver_version": "GPU driver version",
    "gpu_vram_gb": "GPU memory (GB)",
    "gpu_pci_ids": "GPU PCI IDs",
    "gpu_vendors": "GPU vendors",
    "gpu_driver_missing": "GPU driver missing",
    "cpu_name": "CPU",
    "cpu_manufacturer": "CPU maker",
    "cpu_cores": "CPU cores",
    "cpu_logical_cores": "CPU logical cores",
    "npu_name": "NPU",
    "npu_available": "NPU available",
    "ram_total_gb": "memory (GB)",
    "ram_type": "memory type",
    "storage_type": "storage type",
    "storage_capacity_gb": "storage (GB)",
    "isenrolled": "enrolled in MDM",
    "isdomainjoined": "domain joined",
}

_COMPARISONS = {
    "==": "is",
    "EQUALS": "is",
    "!=": "is not",
    "NOT_EQUALS": "is not",
    "<": "is less than",
    "LESS_THAN": "is less than",
    "<=": "is at most",
    "LESS_THAN_OR_EQUAL": "is at most",
    ">": "is more than",
    "GREATER_THAN": "is more than",
    ">=": "is at least",
    "GREATER_THAN_OR_EQUAL": "is at least",
    "LIKE": "matches the pattern",
    "CONTAINS": "contains",
    "DOES_NOT_CONTAIN": "does not contain",
    "BEGINSWITH": "begins with",
    "ENDSWITH": "ends with",
    "IN": "is one of",
}
# ANY accepts only these.
_ANY_OPERATORS = {"==", "EQUALS", "!=", "NOT_EQUALS", "CONTAINS"}

_TOKEN = re.compile(
    r"""
    (?P<space>\s+)
  | (?P<string>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
  | (?P<number>-?\d+(?:\.\d+)?)
  | (?P<op>==|!=|<=|>=|[<>(){},])
  | (?P<word>[A-Za-z0-9_.$@:\\-][A-Za-z0-9_.$@:\\-]*)
    """,
    re.VERBOSE,
)


class ConditionError(ValueError):
    def __init__(self, message: str, column: int) -> None:
        super().__init__(f"{message} (column {column})")
        self.message = message
        self.column = column


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    column: int


@dataclass
class Node:
    """One parsed expression."""

    kind: str  # "and", "or", "not", "compare", "value", "key", "list", "cast"
    text: str = ""
    children: list[Node] = field(default_factory=lambda: [])
    modifier: str = ""
    quantifier: str = ""


@dataclass(frozen=True)
class ConditionReport:
    text: str
    rule: str | None
    error: str | None
    column: int | None
    facts: list[str]
    unknown_facts: list[str]


def _tokens(text: str) -> list[Token]:
    tokens: list[Token] = []
    position = 0
    while position < len(text):
        match = _TOKEN.match(text, position)
        if not match:
            raise ConditionError(f"Unexpected character {text[position]!r}", position + 1)
        kind = match.lastgroup or ""
        if kind != "space":
            tokens.append(Token(kind, match.group(), position + 1))
        position = match.end()
    tokens.append(Token("end", "", len(text) + 1))
    return tokens


class _Parser:
    def __init__(self, text: str) -> None:
        self.tokens = _tokens(text)
        self.position = 0

    def peek(self) -> Token:
        return self.tokens[self.position]

    def take(self) -> Token:
        token = self.tokens[self.position]
        self.position += 1
        return token

    def word(self, *words: str) -> bool:
        token = self.peek()
        return token.kind == "word" and token.text.upper() in words

    def expect(self, text: str) -> Token:
        token = self.take()
        if token.text != text:
            found = token.text or "the end"
            raise ConditionError(f"Expected {text!r} but found {found!r}", token.column)
        return token

    def parse(self) -> Node:
        node = self.parse_or()
        if self.peek().kind != "end":
            raise ConditionError(f"Unexpected {self.peek().text!r}", self.peek().column)
        return node

    def parse_or(self) -> Node:
        node = self.parse_and()
        while self.word("OR"):
            self.take()
            node = Node("or", children=[node, self.parse_and()])
        return node

    def parse_and(self) -> Node:
        node = self.parse_not()
        while self.word("AND"):
            self.take()
            node = Node("and", children=[node, self.parse_not()])
        return node

    def parse_not(self) -> Node:
        if self.word("NOT"):
            self.take()
            return Node("not", children=[self.parse_not()])
        if self.peek().text == "(":
            self.take()
            node = self.parse_or()
            self.expect(")")
            return node
        return self.parse_comparison()

    def parse_comparison(self) -> Node:
        quantifier = ""
        if self.word("ANY"):
            quantifier = self.take().text.upper()
        left = self.parse_fact()
        token = self.peek()
        operator = token.text.upper() if token.kind == "word" else token.text
        if operator not in _COMPARISONS:
            found = token.text or "the end"
            raise ConditionError(f"Expected a comparison but found {found!r}", token.column)
        if quantifier and operator not in _ANY_OPERATORS:
            raise ConditionError(f"ANY does not support {token.text!r}", token.column)
        self.take()
        right = self.parse_operand()
        return Node("compare", operator, [left, right], "", quantifier)

    def parse_fact(self) -> Node:
        token = self.take()
        if token.kind != "word" or token.text[:1].isdigit():
            found = token.text or "the end"
            raise ConditionError(f"Expected a fact name but found {found!r}", token.column)
        return Node("key", token.text)

    def parse_operand(self) -> Node:
        """A value: quoted, a number, a boolean, a {…} or (…) list, or a bare word."""
        token = self.take()
        if token.kind in ("string", "number"):
            return Node("value", token.text)
        if token.text in ("{", "("):
            closing = "}" if token.text == "{" else ")"
            items: list[Node] = []
            while self.peek().text != closing:
                items.append(self.parse_operand())
                if self.peek().text == ",":
                    self.take()
                elif self.peek().text != closing:
                    raise ConditionError(f"Expected ',' or {closing!r}", self.peek().column)
            self.take()
            return Node("list", children=items)
        if token.kind == "word":
            upper = token.text.upper()
            if upper in ("TRUE", "FALSE"):
                return Node("value", upper.lower())
            return Node("value", repr(token.text))
        found = token.text or "the end"
        raise ConditionError(f"Expected a value but found {found!r}", token.column)


def parse(text: str) -> Node:
    return _Parser(text).parse()


def _facts(node: Node) -> list[str]:
    found: list[str] = []
    if node.kind == "key":
        found.append(node.text.split(".")[0])
    for child in node.children:
        found += _facts(child)
    return found


def _describe(node: Node) -> str:
    match node.kind:
        case "and":
            return " and ".join(_group(c, "or") for c in node.children)
        case "or":
            return " or ".join(_group(c, "and") for c in node.children)
        case "not":
            return f"not ({_describe(node.children[0])})"
        case "key":
            return KNOWN_FACTS.get(node.text, node.text)
        case "list":
            return "[" + ", ".join(_describe(c) for c in node.children) + "]"
        case "compare":
            left, right = node.children
            phrase = _COMPARISONS[node.text]
            if "c" in node.modifier:
                phrase += " (ignoring case)"
            quantifier = {
                "ANY": "any ",
                "SOME": "any ",
                "ALL": "every ",
                "NONE": "no ",
            }.get(node.quantifier, "")
            return f"{quantifier}{_describe(left)} {phrase} {_describe(right)}"
        case _:
            return node.text


def _group(node: Node, other: str) -> str:
    text = _describe(node)
    return f"({text})" if node.kind == other else text


def analyze(text: str) -> ConditionReport:
    try:
        tree = parse(text)
    except ConditionError as error:
        return ConditionReport(text, None, error.message, error.column, [], [])
    facts = list(dict.fromkeys(_facts(tree)))
    unknown = [f for f in facts if f not in KNOWN_FACTS]
    return ConditionReport(text, _describe(tree), None, None, facts, unknown)
