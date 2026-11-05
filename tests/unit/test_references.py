import shutil
from pathlib import Path

import pytest
from tests.fixtures.build_repo_fixture import REPO

from cimian_web_studio import platform
from cimian_web_studio.repository.config import Repository
from cimian_web_studio.repository.index import Index
from cimian_web_studio.repository.references import Issue, graph_for, validate
from cimian_web_studio.repository.scanner import scan


@pytest.fixture
def scanned(tmp_path: Path) -> tuple[Repository, Index]:
    root = tmp_path / "repo"
    shutil.copytree(REPO, root)
    repo = Repository(id="fixture", name="Fixture", root=root.resolve())
    index = Index(tmp_path / "index.sqlite")
    scan(repo, index)
    return repo, index


def codes(issues: list[Issue], code: str) -> set[tuple[str, str | None]]:
    return {(i.path, i.target) for i in issues if i.code == code}


def test_where_used_finds_manifests_and_dependents(scanned: tuple[Repository, Index]) -> None:
    repo, index = scanned
    graph = graph_for(index, repo)
    used = {(r.source, r.field) for r in graph.where_used("ExampleEditor")}
    assert ("manifests/groups/design-lab.yaml", "managed_installs") in used
    assert ("pkgsinfo/apps/creative/ExampleEditorPlugin-1.0.yaml", "update_for") in used
    plugin = graph.where_used("ExampleEditorPlugin")
    assert plugin[0].condition == "hostname contains 'LAB-' AND arch == 'arm64'"
    runtime = {r.condition for r in graph.where_used("ExampleRuntime")}
    assert "department == 'IT'" in runtime
    assert "manifests/groups/design-lab.yaml" in {
        r.source for r in graph.where_used("site_default")
    }


def test_validation_reports_every_fixture_problem(scanned: tuple[Repository, Index]) -> None:
    repo, index = scanned
    issues = validate(index, repo)
    assert {p for p, _ in codes(issues, "parse-error")} >= {
        "pkgsinfo/invalid/Broken-1.0.yaml",
        "pkgsinfo/invalid/NotAMapping-1.0.yaml",
    }
    assert ("manifests/groups/broken-refs.yaml", "groups/does-not-exist") in codes(
        issues, "missing-manifest"
    )
    missing = codes(issues, "missing-package")
    assert ("manifests/groups/broken-refs.yaml", "ExampleMissing") in missing
    assert ("manifests/groups/design-lab.yaml", "ExampleLegacy") in missing
    cycles = [i for i in issues if i.code == "include-cycle"]
    assert len(cycles) == 1 and "groups/loop-a" in cycles[0].message
    payloads = codes(issues, "missing-payload")
    assert (
        "pkgsinfo/apps/creative/ExampleEditor-2.10.yaml",
        "pkgs/apps/creative/ExampleEditor-2.10.msi",
    ) in payloads


def test_payload_follows_cimian_location_rules() -> None:
    assert platform.summarize("pkginfo", {"installer": {"location": "/apps\\x.msi"}})[
        "payload"
    ] == ("pkgs/apps/x.msi")
    windows = platform.summarize(
        "pkginfo", {"uninstaller": [{"location": "%ProgramFiles%\\Example\\uninstall.exe"}]}
    )
    assert windows["payload"] is None and windows["payloads"] == []


def test_present_payloads_are_not_reported(scanned: tuple[Repository, Index]) -> None:
    repo, index = scanned
    payload = repo.root / "pkgs/apps/creative/ExampleEditor-2.10.msi"
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_bytes(b"")
    paths = {p for p, _ in codes(validate(index, repo), "missing-payload")}
    assert "pkgsinfo/apps/creative/ExampleEditor-2.10.yaml" not in paths
