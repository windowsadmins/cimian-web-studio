import difflib
from pathlib import Path

import pytest

from cimian_web_studio.codec import Append, ParseError, Set, edit, load

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CODEC = FIXTURES / "codec"
REPO = FIXTURES / "repo"


def changed_lines(before: bytes, after: bytes) -> int:
    diff = difflib.unified_diff(
        before.decode().splitlines(), after.decode().splitlines(), lineterm="", n=0
    )
    return sum(1 for line in diff if line[:1] in "+-" and not line.startswith(("+++", "---")))


def yaml_files() -> list[Path]:
    files = [p for p in sorted(REPO.rglob("*.yaml")) if "invalid" not in p.parts]
    return [*files, CODEC / "pkginfo.yaml", CODEC / "manifest.yaml"]


def first_string_path(data: dict[str, object]) -> tuple[str | int, ...]:
    for key, value in data.items():
        if isinstance(value, str) and "\n" not in value:
            return (key,)
    for key, value in data.items():
        if isinstance(value, list) and value and isinstance(value[0], str):
            return (key, 0)
    raise AssertionError("no editable string")


def read(data: dict[str, object], where: tuple[str | int, ...]) -> object:
    value: object = data
    for key in where:
        value = value[key]  # type: ignore[index]
    return value


def test_reads_cimian_text_fields_as_written() -> None:
    doc = load((CODEC / "pkginfo.yaml").read_bytes())
    assert doc.data["version"] == "2.10"
    assert doc.data["installer"]["hash"] == "0" * 64
    assert doc.data["minimum_os_version"] == "10.0.19045"
    assert doc.data["installs"][0]["version"] == "2.10.0.0"
    assert doc.data["installed_size"] == 9007199254740993
    assert doc.data["unattended_install"] is True
    assert doc.data["x_unknown_site_key"]["nested"] == [1, 2.5, "three"]
    unquoted = load(b"name: Example\nversion: 2.10\ninstaller:\n  hash: 000\n")
    assert unquoted.data["version"] == "2.10"
    assert unquoted.data["installer"]["hash"] == "000"


@pytest.mark.parametrize("path", yaml_files(), ids=lambda p: p.name)
def test_no_op_edit_is_byte_identical(path: Path) -> None:
    doc = load(path.read_bytes())
    assert edit(doc, []).raw == doc.raw
    first_key = next(iter(doc.data))
    assert edit(doc, [Set((first_key,), doc.data[first_key])]).raw == doc.raw


@pytest.mark.parametrize("path", yaml_files(), ids=lambda p: p.name)
def test_single_value_edit_changes_two_lines(path: Path) -> None:
    doc = load(path.read_bytes())
    where = first_string_path(doc.data)
    current = read(doc.data, where)
    assert isinstance(current, str)
    result = edit(doc, [Set(where, current + " Pro")])
    assert result.surgical
    assert changed_lines(doc.raw, result.raw) == 2
    assert read(load(result.raw).data, where) == current + " Pro"


def test_comments_and_blank_lines_survive_edits() -> None:
    path = REPO / "pkgsinfo/apps/creative/ExampleEditor-2.10.yaml"
    doc = load(path.read_bytes())
    result = edit(doc, [Set(("display_name",), "Example Editor Pro")])
    assert result.raw.count(b"\n\n") == doc.raw.count(b"\n\n")
    assert b"# quoted: must stay a string, not 2.1" in result.raw
    assert b"# Hand-maintained pkginfo" in result.raw
    version = edit(doc, [Set(("version",), "2.11")])
    assert changed_lines(doc.raw, version.raw) == 2
    assert b'version: "2.11"   # quoted' in version.raw


def test_append_adds_one_line() -> None:
    doc = load((REPO / "manifests/site_default.yaml").read_bytes())
    result = edit(doc, [Append(("managed_installs",), "ExampleExtra")])
    assert result.surgical
    assert changed_lines(doc.raw, result.raw) == 1


def test_windows_paths_round_trip() -> None:
    doc = load((REPO / "pkgsinfo/apps/browsers/ExampleBrowser-135.0.yaml").read_bytes())
    path = ("installs", 0, "path")
    assert read(doc.data, path) == "%ProgramFiles%\\Example\\Browser\\browser.exe"
    result = edit(doc, [Set(path, "%ProgramFiles%\\Example\\Browser 2\\browser.exe")])
    assert result.surgical
    assert read(load(result.raw).data, path) == "%ProgramFiles%\\Example\\Browser 2\\browser.exe"


def test_new_keys_fall_back_to_a_verified_rewrite() -> None:
    doc = load((CODEC / "pkginfo.yaml").read_bytes())
    result = edit(doc, [Set(("notes",), "new key")])
    assert not result.surgical
    assert load(result.raw).data["notes"] == "new key"
    assert load(result.raw).data["installer"]["hash"] == "0" * 64


def test_invalid_files_report_a_location() -> None:
    with pytest.raises(ParseError) as error:
        load((REPO / "pkgsinfo/invalid/Broken-1.0.yaml").read_bytes())
    assert error.value.line == 3


def test_rejects_yaml_aliases_and_alias_bombs() -> None:
    bomb = b"a: &a [x, x, x, x, x, x, x, x, x]\nb: &b [*a, *a, *a, *a, *a, *a, *a, *a, *a]\n"
    with pytest.raises(ParseError, match="aliases"):
        load(bomb)


def test_rejects_deep_nesting() -> None:
    with pytest.raises(ParseError, match="Nesting"):
        load(b"k: " + b"[" * 200 + b"]" * 200 + b"\n")


def test_rejects_oversized_files() -> None:
    with pytest.raises(ParseError, match="larger than"):
        load(b"#" * (17 * 1024 * 1024))


def test_revision_tracks_bytes() -> None:
    raw = (CODEC / "pkginfo.yaml").read_bytes()
    assert load(raw).revision == load(raw).revision
    assert load(raw).revision != load(raw + b"\n").revision


def test_flow_list_items_edit_in_place() -> None:
    doc = load(b"catalogs: [testing, production]  # both\nname: x\n")
    result = edit(doc, [Set(("catalogs", 1), "prod, eu")])
    assert result.surgical
    assert result.raw == b'catalogs: [testing, "prod, eu"]  # both\nname: x\n'
    assert load(result.raw).data["catalogs"] == ["testing", "prod, eu"]


def test_block_lists_are_replaced_in_place() -> None:
    raw = b"catalogs:\n  - testing   # first\n  - production\n\nrequires:\n  - x\n"
    doc = load(raw)
    result = edit(doc, [Set(("catalogs",), ["testing", "staging"])])
    assert result.surgical
    assert result.raw == b"catalogs:\n  - testing   # first\n  - staging\n\nrequires:\n  - x\n"
    shorter = edit(doc, [Set(("catalogs",), ["testing"])])
    assert shorter.raw == b"catalogs:\n  - testing   # first\n\nrequires:\n  - x\n"


def test_changes_that_do_not_fit_are_codec_errors() -> None:
    from cimian_web_studio.codec import CodecError

    doc = load(b"name: x\nlist: [a]\n")
    for change in (Append(("name",), "y"), Set(("missing", "deeper"), 1), Set(("list", 5), "z")):
        with pytest.raises(CodecError, match="does not fit"):
            edit(doc, [change])
