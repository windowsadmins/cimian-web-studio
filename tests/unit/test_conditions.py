import pytest

from cimian_web_studio.conditions import analyze


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        (
            "hostname CONTAINS Design- AND arch == x64",
            "hostname contains 'Design-' and architecture is 'x64'",
        ),
        ("hostname DOES_NOT_CONTAIN Camera", "hostname does not contain 'Camera'"),
        (
            'NOT hostname CONTAINS "Kiosk" AND (domain == "CORP" OR domain == "EDU")',
            'not (hostname contains "Kiosk") and (domain is "CORP" or domain is "EDU")',
        ),
        ("isenrolled == true", "enrolled in MDM is true"),
        (
            "os_vers_major >= 11 AND arch EQUALS x64",
            "Windows major version is at least 11 and architecture is 'x64'",
        ),
        ("arch IN (x64, arm64)", "architecture is one of ['x64', 'arm64']"),
        (
            "hostname contains 'LAB-' AND arch == 'arm64'",
            "hostname contains 'LAB-' and architecture is 'arm64'",
        ),
    ],
)
def test_conditions_read_as_rules(text: str, rule: str) -> None:
    report = analyze(text)
    assert report.error is None
    assert report.rule == rule


def test_any_reads_and_is_limited() -> None:
    assert analyze('ANY catalogs != "Testing"').rule
    report = analyze("ANY catalogs LIKE x")
    assert report.error and "ANY" in report.error and report.column == 14


def test_custom_facts_are_reported_but_allowed() -> None:
    report = analyze("department == 'IT'")
    assert report.rule == "department is 'IT'"
    assert report.unknown_facts == ["department"]


@pytest.mark.parametrize(
    ("text", "column"),
    [
        ("os_vers_major >= 11 AND", 24),
        ("hostname BEGINS x", 10),
        ("(arch == x64", 13),
        ("== x64", 1),
    ],
)
def test_syntax_errors_carry_a_column(text: str, column: int) -> None:
    report = analyze(text)
    assert report.rule is None and report.error
    assert report.column == column
