import hashlib
import re
from pathlib import Path

from tests.fixtures.build_repo_fixture import REPO
from tests.fixtures.generate_large_repo import generate


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_generator_is_deterministic(tmp_path: Path) -> None:
    generate(tmp_path / "a", pkginfo=60, manifests=20, seed=7)
    generate(tmp_path / "b", pkginfo=60, manifests=20, seed=7)
    assert tree_digest(tmp_path / "a") == tree_digest(tmp_path / "b")
    assert len(list((tmp_path / "a" / "pkgsinfo").rglob("*.yaml"))) == 60
    assert len(list((tmp_path / "a" / "manifests").rglob("*.yaml"))) == 20


def test_repo_fixture_has_the_cases_later_slices_need() -> None:
    pkgsinfo = REPO / "pkgsinfo"
    assert len(list(pkgsinfo.rglob("ExampleBrowser-136.0.yaml"))) == 2
    editor = (pkgsinfo / "apps/creative/ExampleEditor-2.10.yaml").read_text()
    assert 'version: "2.10"' in editor
    assert "# Hand-maintained" in editor
    assert "%ProgramFiles%" in (pkgsinfo / "apps/browsers/ExampleBrowser-135.0.yaml").read_text()
    design_lab = (REPO / "manifests/groups/design-lab.yaml").read_text()
    assert "condition:" in design_lab
    assert "fact: department" in design_lab


def test_repo_fixture_uses_lf_line_endings() -> None:
    for path in REPO.rglob("*.yaml"):
        assert b"\r\n" not in path.read_bytes(), path


def test_repo_fixture_contains_no_real_identifiers() -> None:
    text = b"".join(p.read_bytes() for p in REPO.rglob("*") if p.is_file())
    for marker in (b"ecuad", b"emilycarr", b"focused.systems"):
        assert marker not in text.lower()
    assert re.search(rb"[\w.+-]+@[\w-]+\.[\w.]+", text) is None
