"""Generating catalogs: they replace the repository's catalogs only after the
worker's output checks out, and a failed generation leaves the old ones."""

import hashlib
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.fixtures.build_repo_fixture import REPO
from tests.unit.test_worker import (
    BROKEN_PKGINFO,
    FAILING_TOOL,
    FAKE_TOOL,
    REAL_MAKECATALOGS,
    TOKEN,
    fake,
    only,
    posix_only,
    repo_copy,
    submit,
    wait_for,
    windows_only,
    worker_for,
)

from cimian_web_studio import catalogs
from cimian_web_studio.app import create_app
from cimian_web_studio.codec import load
from cimian_web_studio.jobs.apply import recover_swaps, swap_folder
from cimian_web_studio.repository.config import Repository, Settings, WorkerEntry
from cimian_web_studio.worker import Tools

STALE = b"items:\r\n  - name: Stale\r\n    version: 1\r\n"


def tree(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


@pytest.fixture
def root(tmp_path: Path) -> Path:
    copy = repo_copy(tmp_path)
    (copy / "catalogs" / "stale.yaml").write_bytes(STALE)
    return copy


def make_studio(tmp_path: Path, root: Path, **options: Any) -> Iterator[TestClient]:
    repo = replace(Repository(id="fixture", name="Fixture", root=root, writable=True), **options)
    settings = Settings(
        repositories=(repo,),
        state_dir=tmp_path / "state",
        rescan_seconds=0,
        workers=(WorkerEntry("win-1", hashlib.sha256(TOKEN.encode()).hexdigest()),),
    )
    with TestClient(
        create_app(settings, static_dir=tmp_path / "none"), base_url="http://localhost"
    ) as client:
        client.headers["X-CSRF-Token"] = client.get("/api/session").json()["csrf_token"]
        yield client


@pytest.fixture
def studio(tmp_path: Path, root: Path) -> Iterator[TestClient]:
    yield from make_studio(tmp_path, root)


def sources(root: Path) -> list[dict[str, Any]]:
    return [load(p.read_bytes()).data for p in sorted((root / "pkgsinfo").rglob("*.yaml"))]


def generated(root: Path, tmp_path: Path) -> Path:
    """The catalogs the studio's model of makecatalogs writes for this repository."""
    out = tmp_path / "out"
    out.mkdir()
    items = [catalogs.expected_item(s) for s in sources(root)]
    named: dict[str, list[dict[str, Any]]] = {catalogs.ALL: items}
    for item in items:
        for name in item.get("catalogs", []):
            named.setdefault(name, []).append(item)
    for name, entries in named.items():
        (out / f"{name}.yaml").write_bytes(catalogs.render(entries))
    return out


# The check itself, on any platform.


def test_the_fixture_catalogs_pass_the_check(root: Path, tmp_path: Path) -> None:
    out = generated(root, tmp_path)
    assert catalogs.check_output(out, sources(root)) == {
        "All": 8,
        "production": 4,
        "testing": 8,
    }


def test_makecatalogs_keeps_its_model_adds_defaults_and_drops_the_rest(root: Path) -> None:
    editor = load((root / "pkgsinfo/apps/creative/ExampleEditor-2.10.yaml").read_bytes()).data
    item = catalogs.expected_item(editor)
    assert catalogs.dropped_keys(editor) == {"installed_size", "x_unknown_site_key"}
    assert item["version"] == "2.10" and item["minimum_os_version"] == "10.0.19045"
    assert item["OnDemand"] is False and item["recurring"] is False
    assert item["unattended_install"] is False and item["unattended_uninstall"] is False
    assert len(item["loop_fingerprint"]) == 16
    duplicate = load(
        (root / "pkgsinfo/apps/browsers/duplicates/ExampleBrowser-136.0.yaml").read_bytes()
    ).data
    assert "notes" not in catalogs.expected_item(duplicate)


@pytest.mark.parametrize(
    "rewrite,reason",
    [
        (lambda b: b.replace(b"items:\r\n", b"# note\r\nitems:\r\n", 1), "form makecatalogs"),
        (lambda b: b.replace(b"\r\n", b"\n", 3), "form makecatalogs"),
        (lambda b: b.replace(b"    version: 5.0", b"    version: '5.0'", 1), "form makecatalogs"),
        (lambda b: b.replace(b"  - name:", b"  - &a\r\n    name:", 1), "anchors"),
        (lambda b: b + b"  - *a\r\n", "aliases"),
        (lambda b: b.replace(b"    version: 5.0", b"    version: !!str 5.0", 1), "tags"),
        (lambda b: b.replace(b"    category:", b"    name: X\r\n    category:", 1), "duplicate"),
        (lambda b: b + b"---\r\nitems: []\r\n", "one implicit document"),
        (lambda b: b"items:\r\n  - [not, a, mapping]\r\n", "must be a mapping"),
        (lambda b: b.replace(b"    OnDemand: false", b"    OnDemand: no", 1), "true or false"),
        (lambda b: b.replace(b"    recurring: false", b"    surprise: 1", 1), "does not write"),
        (lambda b: b.replace(b"    category:", b"    identifier: ~\r\n    category:", 1), "null"),
        (lambda b: b"\xff" + b, "not UTF-8"),
    ],
)
def test_catalogs_must_be_exactly_what_makecatalogs_writes(
    root: Path, tmp_path: Path, rewrite: Any, reason: str
) -> None:
    out = generated(root, tmp_path)
    target = out / "production.yaml"
    target.write_bytes(rewrite(target.read_bytes()))
    with pytest.raises(catalogs.CatalogError, match=r"production\.yaml cannot be read") as error:
        catalogs.check_output(out, sources(root))
    assert reason in str(error.value)


def test_the_canonical_form_round_trips_with_either_line_ending(root: Path, tmp_path: Path) -> None:
    raw = (generated(root, tmp_path) / "All.yaml").read_bytes()
    items = catalogs.canonical(raw)
    assert catalogs.render(items) == raw
    assert catalogs.canonical(raw.replace(b"\r\n", b"\n")) == items


def test_names_and_files() -> None:
    assert catalogs.name_of("catalogs/testing.yaml") == "testing"
    assert catalogs.file_for(catalogs.ALL) == "catalogs/All.yaml"


def test_same_checks_types() -> None:
    assert catalogs.same({"a": [1, "x"]}, {"a": [1, "x"]})
    assert not catalogs.same(True, 1) and not catalogs.same(1, 1.0)
    assert not catalogs.same({"a": "1"}, {"a": 1}) and not catalogs.same([1], [1, 1])


# Generation through the worker. The fake makecatalogs is a Python script, so
# these run on Linux and macOS; Windows runs the real tool below.


@posix_only
def test_generated_catalogs_replace_the_old_ones(
    studio: TestClient, tmp_path: Path, root: Path
) -> None:
    worker = worker_for(studio, only(tmp_path, FAKE_TOOL))
    worker.hello()
    job_id = submit(studio).json()["id"]
    assert worker.run_once()
    job = wait_for(studio, job_id, "succeeded")
    counts = job["result"]["applied"]["counts"]
    assert counts == {"All": 8, "production": 4, "testing": 8}
    assert sorted(tree(root / "catalogs")) == [
        ".gitkeep",
        "All.yaml",
        "production.yaml",
        "testing.yaml",
    ]
    assert b"name: ExampleEditor" in (root / "catalogs" / "All.yaml").read_bytes()
    assert not list(root.glob(".catalogs.studio-*"))
    listed = studio.get("/api/repositories/fixture/catalogs").json()
    assert "stale" not in [c["name"] for c in listed]
    assert all(c["up_to_date"] for c in listed)


@posix_only
def test_a_failed_tool_keeps_the_last_catalogs(
    studio: TestClient, tmp_path: Path, root: Path
) -> None:
    before = tree(root / "catalogs")
    worker = worker_for(studio, only(tmp_path, FAILING_TOOL))
    worker.hello()
    job_id = submit(studio).json()["id"]
    assert worker.run_once()
    assert "exited with status 3" in wait_for(studio, job_id, "failed")["error"]
    assert tree(root / "catalogs") == before


def test_a_broken_pkginfo_fails_generation_and_keeps_the_last_catalogs(
    tmp_path: Path,
) -> None:
    """makecatalogs refuses to write catalogs while any pkginfo fails to parse,
    and the studio does not pass --tolerate_parse_errors, so the job fails."""
    root = repo_copy(tmp_path, broken=True)
    (root / "catalogs" / "stale.yaml").write_bytes(STALE)
    real = REAL_MAKECATALOGS.is_file()
    if not real and sys.platform == "win32":
        pytest.skip("needs Cimian's makecatalogs")
    for studio in make_studio(tmp_path, root):
        before = tree(root / "catalogs")
        tools = Tools.probe() if real else only(tmp_path, FAKE_TOOL)
        worker = worker_for(studio, tools)
        worker.hello()
        job_id = submit(studio).json()["id"]
        assert worker.run_once()
        error = wait_for(studio, job_id, "failed")["error"]
        assert "exited with status 1" in error and "Broken-1.0.yaml" in error
        assert tree(root / "catalogs") == before


@posix_only
@pytest.mark.parametrize(
    "tamper,extra,reason",
    [
        ('item["installer"]["location"] = "evil.exe"', "", "does not match any pkginfo"),
        ('item["preinstall_script"] = "Start-Process evil"', "", "does not match any pkginfo"),
        (
            'item["installer"]["arguments"] = ["/evil"]\n'
            '    item["loop_fingerprint"] = model.fingerprint(item)',
            "",
            "does not match any pkginfo",
        ),
        ('item["unattended_install"] = 1', "", "must be true or false"),
        ('item["loop_fingerprint"] = "0" * 16', "", "does not match any pkginfo"),
        (
            "",
            'catalogs["All"].append(model.expected_item({"name": "Injected", "version": "1"}))',
            "Injected 1 does not",
        ),
        ("", 'catalogs["All"].pop()', "is missing"),
        ("", 'catalogs["everyone"] = []', "not a catalog any pkginfo names"),
        ("", 'del catalogs["production"]', "No catalog was generated for production"),
        ("", 'catalogs["testing"].append(dict(catalogs["testing"][0]))', "does not match"),
        ("", 'catalogs["testing"][0] = {}', "does not match"),
    ],
)
def test_a_worker_cannot_change_what_clients_install(
    studio: TestClient, tmp_path: Path, root: Path, tamper: str, extra: str, reason: str
) -> None:
    before = tree(root / "catalogs")
    worker = worker_for(studio, only(tmp_path, fake(tamper, extra)))
    worker.hello()
    job_id = submit(studio).json()["id"]
    assert worker.run_once()
    error = wait_for(studio, job_id, "failed")["error"]
    assert error.startswith("The catalogs were not replaced") and reason in error
    assert tree(root / "catalogs") == before


@posix_only
def test_a_non_canonical_file_from_the_worker_is_refused(
    studio: TestClient, tmp_path: Path, root: Path
) -> None:
    before = tree(root / "catalogs")
    extra = (
        'out = staging / "catalogs"\n'
        "out.mkdir()\n"
        "for name, items in catalogs.items():\n"
        "    data = model.render(items)\n"
        "    if name == 'production':\n"
        "        data = data.replace(b'items:', b'# note\\r\\nitems:', 1)\n"
        '    (out / f"{name}.yaml").write_bytes(data)\n'
        "sys.exit(0)"
    )
    worker = worker_for(studio, only(tmp_path, fake(extra=extra)))
    worker.hello()
    job_id = submit(studio).json()["id"]
    assert worker.run_once()
    error = wait_for(studio, job_id, "failed")["error"]
    assert "production.yaml cannot be read" in error and "form makecatalogs" in error
    assert tree(root / "catalogs") == before


@posix_only
def test_read_only_and_live_repositories(tmp_path: Path, root: Path) -> None:
    for client in make_studio(tmp_path / "ro", root, writable=False):
        refused = client.post(
            "/api/repositories/fixture/jobs", json={"operation": "catalog.generate"}
        )
        assert refused.status_code in (403, 409)
    worker_tools = only(tmp_path, FAKE_TOOL)
    for client in make_studio(tmp_path / "live", root, live=True):
        worker_for(client, worker_tools).hello()
        assert submit(client).status_code == 428
        ok = client.post(
            "/api/repositories/fixture/jobs",
            json={"operation": "catalog.generate", "arguments": {"acknowledge_live": True}},
        )
        assert ok.status_code == 201


def test_a_swap_interrupted_half_way_is_undone(tmp_path: Path, root: Path) -> None:
    repo = Repository(id="fixture", name="Fixture", root=root, writable=True)
    before = tree(root / "catalogs")
    (root / "catalogs").rename(root / ".catalogs.studio-old-abcd")
    (root / ".catalogs.studio-new-abcd").mkdir()
    assert recover_swaps(repo, "catalogs") == [
        "restored catalogs from .catalogs.studio-old-abcd",
        "removed .catalogs.studio-new-abcd",
    ]
    assert tree(root / "catalogs") == before
    new = tmp_path / "new"
    new.mkdir()
    (new / "All.yaml").write_bytes(b"x")
    swap_folder(repo, "catalogs", new, tmp_path / "journal")
    assert tree(root / "catalogs") == {".gitkeep": b"", "All.yaml": b"x"}
    assert recover_swaps(repo, "catalogs") == []


def test_catalogs_view_shows_membership_and_what_is_out_of_date(
    studio: TestClient, root: Path, tmp_path: Path
) -> None:
    listed = {c["name"]: c for c in studio.get("/api/repositories/fixture/catalogs").json()}
    assert listed["stale"]["expected"] == 0 and not listed["stale"]["up_to_date"]
    # Both ExampleBrowser 136.0 pkginfo count, as makecatalogs lists both.
    assert listed["All"]["error"] == "Not generated yet" and listed["All"]["expected"] == 8
    for path in generated(root, tmp_path).iterdir():
        shutil.copy(path, root / "catalogs" / path.name)
    studio.post("/api/repositories/fixture/rescan").raise_for_status()
    testing = studio.get("/api/repositories/fixture/catalogs/testing").json()
    assert testing["up_to_date"] and all(m["pkginfo"] for m in testing["members"])
    everything = studio.get("/api/repositories/fixture/catalogs/All").json()
    assert everything["up_to_date"] and everything["items"] == everything["expected"] == 8
    editor = root / "pkgsinfo/apps/creative/ExampleEditor-2.10.yaml"
    editor.write_bytes(editor.read_bytes().replace(b"  - production", b"  - staging", 1))
    studio.post("/api/repositories/fixture/rescan").raise_for_status()
    staging = studio.get("/api/repositories/fixture/catalogs/staging").json()
    assert staging["path"] is None and staging["error"] == "Not generated yet"
    assert [m["name"] for m in staging["missing"]] == ["ExampleEditor"]
    production = studio.get("/api/repositories/fixture/catalogs/production").json()
    assert not production["up_to_date"]
    assert "ExampleEditor" in [m["name"] for m in production["extra"]]
    assert studio.get("/api/repositories/fixture/catalogs/nope").status_code == 404


# The real makecatalogs, on Windows.


def run_makecatalogs(repo: Path) -> None:
    command = [str(REAL_MAKECATALOGS), "--repo_path", str(repo), "--skip_payload_check"]
    subprocess.run(command, check=True, capture_output=True)  # noqa: S603


@windows_only
def test_the_studio_model_matches_makecatalogs_byte_for_byte(root: Path) -> None:
    run_makecatalogs(root)
    for path in sorted((root / "catalogs").glob("*.yaml")):
        if path.name == "stale.yaml":
            continue
        raw = path.read_bytes()
        assert catalogs.render(catalogs.canonical(raw)) == raw
    assert catalogs.check_output(root / "catalogs", sources(root)) == {
        "All": 8,
        "production": 4,
        "testing": 8,
    }


@windows_only
def test_output_matches_running_makecatalogs_directly(
    studio: TestClient, root: Path, tmp_path: Path
) -> None:
    direct = tmp_path / "direct"
    shutil.copytree(root, direct)
    run_makecatalogs(direct)
    worker = worker_for(studio, Tools.probe())
    worker.hello()
    job_id = submit(studio).json()["id"]
    assert worker.run_once()
    wait_for(studio, job_id, "succeeded")
    assert tree(root / "catalogs") == tree(direct / "catalogs")
    listed = studio.get("/api/repositories/fixture/catalogs").json()
    assert [c["name"] for c in listed] == ["All", "production", "testing"]
    assert all(c["up_to_date"] for c in listed)


@windows_only
def test_the_broken_fixture_is_what_makes_makecatalogs_fail(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(REPO, root)
    with pytest.raises(subprocess.CalledProcessError) as failed:
        run_makecatalogs(root)
    assert failed.value.returncode == 1 and b"tolerate_parse_errors" in failed.value.stderr
    shutil.rmtree(root / BROKEN_PKGINFO)
    run_makecatalogs(root)
