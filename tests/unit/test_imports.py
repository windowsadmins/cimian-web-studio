"""Imports: resumable uploads, makepkginfo on the worker, and a reviewed draft
that adds the pkginfo and the installer together."""

import hashlib
import shutil
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.fixtures.build_repo_fixture import REPO
from tests.unit.test_worker import TOKEN, posix_only

from cimian_web_studio.app import create_app
from cimian_web_studio.changes.apply import commit, recover
from cimian_web_studio.codec import load
from cimian_web_studio.repository.config import Repository, Settings, WorkerEntry
from cimian_web_studio.worker import Tools, Worker

PAYLOAD = b"not really a package" * 5000
REAL_MAKEPKGINFO = Path(r"C:\Program Files\Cimian\makepkginfo.exe")

# A stand-in for makepkginfo: prints a pkginfo for the file it is given.
FAKE_MAKEPKGINFO = """
import hashlib, pathlib, sys
if sys.argv[1] == "--version":
    print("9.9.9-test")
    sys.exit(0)
item = pathlib.Path(sys.argv[1])
data = item.read_bytes()
print("name: Example")
print('version: "1.2.3"')
print("catalogs:")
print("  - testing")
print("installer:")
print("  type: msi")
print(f"  size: {len(data) // 1024}")
print(f"  location: {item.name}")
print(f"  hash: {HASH}")
"""


def fake_tool(tmp_path: Path, hash_expr: str = "hashlib.sha256(data).hexdigest()") -> Path:
    path = tmp_path / "bin" / "makepkginfo"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!{sys.executable}\n" + FAKE_MAKEPKGINFO.replace("HASH", hash_expr))
    path.chmod(0o755)
    return path


@pytest.fixture
def root(tmp_path: Path) -> Path:
    copy = tmp_path / "repo"
    shutil.copytree(REPO, copy)
    return copy


@pytest.fixture
def studio(tmp_path: Path, root: Path) -> Iterator[TestClient]:
    settings = Settings(
        repositories=(Repository(id="fixture", name="Fixture", root=root, writable=True),),
        state_dir=tmp_path / "state",
        rescan_seconds=0,
        workers=(WorkerEntry("mac-1", hashlib.sha256(TOKEN.encode()).hexdigest()),),
    )
    with TestClient(
        create_app(settings, static_dir=tmp_path / "none"), base_url="http://localhost"
    ) as c:
        c.headers["X-CSRF-Token"] = c.get("/api/session").json()["csrf_token"]
        yield c


def upload(studio: TestClient, data: bytes = PAYLOAD, name: str = "Example-1.2.3.msi") -> str:
    created = studio.post(
        "/api/repositories/fixture/uploads",
        json={"filename": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()},
    )
    assert created.status_code == 201, created.text
    upload_id = created.json()["id"]
    sent = studio.patch(
        f"/api/repositories/fixture/uploads/{upload_id}",
        content=data,
        headers={"Upload-Offset": "0"},
    )
    assert sent.json()["complete"], sent.text
    return upload_id


def fake_tools(tmp_path: Path, hash_expr: str = "hashlib.sha256(data).hexdigest()") -> Tools:
    return Tools.probe(
        {"makepkginfo": fake_tool(tmp_path, hash_expr), "makecatalogs": tmp_path / "missing"}
    )


def worker(studio: TestClient, tools: Tools) -> Worker:
    client = TestClient(studio.app, base_url="http://localhost")
    w = Worker(cast(httpx.Client, client), "mac-1", TOKEN, tools, poll_seconds=0.05)
    w.hello()
    return w


def wait(studio: TestClient, job_id: str) -> dict[str, Any]:
    job: dict[str, Any] = {}
    for _ in range(200):
        job = studio.get(f"/api/repositories/fixture/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed", "cancelled"):
            return job
        time.sleep(0.05)
    raise AssertionError(job)


def start_import(studio: TestClient, upload_id: str, subdirectory: str = "apps") -> Any:
    return studio.post(
        "/api/repositories/fixture/jobs",
        json={
            "operation": "package.import",
            "arguments": {"upload": upload_id, "subdirectory": subdirectory},
        },
    )


def test_an_interrupted_upload_resumes(studio: TestClient) -> None:
    digest = hashlib.sha256(PAYLOAD).hexdigest()
    created = studio.post(
        "/api/repositories/fixture/uploads",
        json={"filename": "Example-1.2.3.msi", "size": len(PAYLOAD), "sha256": digest},
    ).json()
    url = f"/api/repositories/fixture/uploads/{created['id']}"
    half = len(PAYLOAD) // 2
    assert (
        studio.patch(url, content=PAYLOAD[:half], headers={"Upload-Offset": "0"}).json()["received"]
        == half
    )
    # The connection drops; the client asks where it got to and carries on.
    status = studio.get(url).json()
    assert status["received"] == half and not status["complete"]
    stale = studio.patch(url, content=PAYLOAD[:10], headers={"Upload-Offset": "0"})
    assert stale.status_code == 409 and str(half) in stale.json()["detail"]
    done = studio.patch(url, content=PAYLOAD[half:], headers={"Upload-Offset": str(half)})
    assert done.json()["complete"]


def test_a_corrupted_upload_is_refused_and_can_be_resent(studio: TestClient) -> None:
    digest = hashlib.sha256(PAYLOAD).hexdigest()
    created = studio.post(
        "/api/repositories/fixture/uploads",
        json={"filename": "Example-1.2.3.msi", "size": len(PAYLOAD), "sha256": digest},
    ).json()
    url = f"/api/repositories/fixture/uploads/{created['id']}"
    bad = studio.patch(url, content=b"x" * len(PAYLOAD), headers={"Upload-Offset": "0"})
    assert bad.status_code == 422 and studio.get(url).json()["received"] == 0
    assert studio.patch(url, content=PAYLOAD, headers={"Upload-Offset": "0"}).json()["complete"]


@pytest.mark.parametrize(
    "name,size,status",
    [
        ("../evil.msi", 10, 400),
        ("CON.msi", 10, 400),
        ("com1.msi", 10, 400),
        ("LPT9.tar.msi", 10, 400),
        ("COM¹.msi", 10, 400),
        ("Example.msi.", 10, 400),
        ("Example.msi ", 10, 400),
        ("Example.pkg", 10, 400),
        ("Ok.msi", 0, 413),
    ],
)
def test_uploads_are_checked_when_declared(
    studio: TestClient, name: str, size: int, status: int
) -> None:
    refused = studio.post(
        "/api/repositories/fixture/uploads",
        json={"filename": name, "size": size, "sha256": "0" * 64},
    )
    assert refused.status_code == status


@posix_only
def test_an_import_arrives_as_a_draft_and_saving_adds_both_files(
    studio: TestClient, tmp_path: Path, root: Path
) -> None:
    w = worker(
        studio, Tools.probe({"makepkginfo": fake_tool(tmp_path), "makecatalogs": tmp_path / "x"})
    )
    upload_id = upload(studio)
    job_id = start_import(studio, upload_id).json()["id"]
    assert w.run_once()
    job = wait(studio, job_id)
    assert job["status"] == "succeeded", job
    draft = job["result"]["draft"]
    assert draft["pkginfo"] == "pkgsinfo/apps/Example-1.2.3.yaml"
    assert draft["payload"] == "pkgs/apps/Example-1.2.3.msi"
    assert not (root / draft["pkginfo"]).exists() and not (root / draft["payload"]).exists()
    change_set = studio.get(f"/api/repositories/fixture/changesets/{draft['change_set']}").json()
    assert change_set["title"] == "Import Example 1.2.3"
    [new_file] = change_set["files"]
    assert (
        new_file["base_revision"] == ""
        and "+  location: apps/Example-1.2.3.msi" in new_file["diff"]
    )
    [payload] = change_set["payloads"]
    assert payload["size"] == len(PAYLOAD) and not payload["conflict"]
    saved = studio.post(f"/api/repositories/fixture/changesets/{draft['change_set']}/save", json={})
    assert saved.status_code == 200, saved.text
    assert (root / draft["payload"]).read_bytes() == PAYLOAD
    pkginfo = load((root / draft["pkginfo"]).read_bytes()).data
    assert pkginfo["installer"]["location"] == "apps/Example-1.2.3.msi"
    names = [p["name"] for p in studio.get("/api/repositories/fixture/packages").json()["items"]]
    assert "Example" in names


@posix_only
def test_a_worker_cannot_describe_a_different_file(
    studio: TestClient, tmp_path: Path, root: Path
) -> None:
    w = worker(
        studio,
        Tools.probe(
            {"makepkginfo": fake_tool(tmp_path, '"0" * 64'), "makecatalogs": tmp_path / "x"}
        ),
    )
    job_id = start_import(studio, upload(studio)).json()["id"]
    assert w.run_once()
    job = wait(studio, job_id)
    assert job["status"] == "failed" and "installer.hash" in job["error"]
    assert studio.get("/api/repositories/fixture/changesets").json() == []


@posix_only
def test_existing_files_are_never_overwritten(
    studio: TestClient, tmp_path: Path, root: Path
) -> None:
    w = worker(studio, fake_tools(tmp_path))
    (root / "pkgsinfo/apps").mkdir(exist_ok=True)
    (root / "pkgsinfo/apps/Example-1.2.3.yaml").write_bytes(b"name: Old\n")
    job_id = start_import(studio, upload(studio)).json()["id"]
    assert w.run_once()
    draft = wait(studio, job_id)["result"]["draft"]
    assert draft["pkginfo"].endswith("Example-1.2.3__1.yaml")
    (root / "pkgs/apps").mkdir(parents=True, exist_ok=True)
    (root / "pkgs/apps/Example-1.2.3.msi").write_bytes(b"someone else's")
    refused = studio.post(
        f"/api/repositories/fixture/changesets/{draft['change_set']}/save", json={}
    )
    assert refused.status_code == 409 and "pkgs/apps/Example-1.2.3.msi" in refused.text
    assert (root / "pkgs/apps/Example-1.2.3.msi").read_bytes() == b"someone else's"
    again = start_import(studio, upload(studio)).json()["id"]
    assert w.run_once()
    assert "already exists" in wait(studio, again)["error"]


def test_imports_need_a_finished_upload_and_a_plain_folder(studio: TestClient) -> None:
    created = studio.post(
        "/api/repositories/fixture/uploads",
        json={"filename": "Example-1.2.3.msi", "size": 10, "sha256": "0" * 64},
    ).json()
    refused = start_import(studio, created["id"])
    assert refused.status_code in (409, 400)
    for folder in ("../escape", "pkgs/apps", "/abs"):
        assert start_import(studio, created["id"], folder).status_code in (400, 409)


def test_a_save_cut_short_after_the_installer_is_finished_on_restart(
    studio: TestClient, tmp_path: Path, root: Path
) -> None:
    app = cast(FastAPI, studio.app)
    changes = app.state.changes  # pyright: ignore[reportAttributeAccessIssue]
    uploads = app.state.uploads  # pyright: ignore[reportAttributeAccessIssue]
    upload_id = upload(studio)
    item = uploads.get(upload_id)
    draft = changes.create("fixture", "local", "Local administrator", "Import")
    from cimian_web_studio.changes.model import Payload

    changes.put_new_file(
        draft.id, "pkgsinfo/apps/Example-1.2.3.yaml", {"name": "Example", "version": "1.2.3"}
    )
    changes.put_payload(
        draft.id, Payload("pkgs/apps/Example-1.2.3.msi", upload_id, item.sha256, item.size)
    )
    repo = app.state.settings.repositories[0]  # pyright: ignore[reportAttributeAccessIssue]
    journal = tmp_path / "journal"
    with pytest.raises(Exception, match="Simulated crash"):
        commit(
            repo,
            changes.get(draft.id),
            journal,
            payload_source=lambda u: uploads.path(uploads.get(u)),
            crash_after=1,
        )
    assert (root / "pkgs/apps/Example-1.2.3.msi").read_bytes() == PAYLOAD
    assert not (root / "pkgsinfo/apps/Example-1.2.3.yaml").exists()
    [report] = recover(repo, journal)
    assert sorted(report.finished) == [
        "pkgs/apps/Example-1.2.3.msi",
        "pkgsinfo/apps/Example-1.2.3.yaml",
    ]
    assert load((root / "pkgsinfo/apps/Example-1.2.3.yaml").read_bytes()).data["name"] == "Example"


@pytest.mark.skipif(not REAL_MAKEPKGINFO.is_file(), reason="needs Cimian's makepkginfo")
def test_real_makepkginfo_on_windows(studio: TestClient, tmp_path: Path) -> None:
    pytest.skip("Filled in on Windows with a real installer")
