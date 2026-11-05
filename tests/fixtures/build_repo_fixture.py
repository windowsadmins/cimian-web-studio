"""Write the synthetic Cimian repository fixture in tests/fixtures/repo.

Every value is invented. The YAML is written as text on purpose: it keeps the
comments, quoting, and layout a hand-maintained repository has, which the codec
must preserve. The output is deterministic and committed.
"""

import shutil
from pathlib import Path

REPO = Path(__file__).parent / "repo"

HASH = "0" * 64

FILES: dict[str, str] = {
    # Two versions of one name, one in production.
    "pkgsinfo/apps/browsers/ExampleBrowser-135.0.yaml": f"""\
name: ExampleBrowser
display_name: Example Browser
version: "135.0"
category: Browsers
developer: Example Co
description: Invented browser package for tests.
catalogs:
  - testing
  - production
installer:
  type: exe
  location: pkgs/apps/browsers/ExampleBrowser-135.0.exe
  hash: {HASH}
  arguments:
    - /S
installs:
  - type: file
    path: '%ProgramFiles%\\Example\\Browser\\browser.exe'
    version: "135.0.0.0"
unattended_install: true
""",
    "pkgsinfo/apps/browsers/ExampleBrowser-136.0.yaml": f"""\
name: ExampleBrowser
display_name: Example Browser
version: "136.0"
category: Browsers
catalogs:
  - testing
installer:
  type: exe
  location: pkgs/apps/browsers/ExampleBrowser-136.0.exe
  hash: {HASH}
installs:
  - type: file
    path: '%ProgramFiles%\\Example\\Browser\\browser.exe'
    version: "136.0.0.0"
""",
    # The same name and version in two files is valid input and must stay visible.
    "pkgsinfo/apps/browsers/duplicates/ExampleBrowser-136.0.yaml": f"""\
name: ExampleBrowser
version: "136.0"
catalogs: [testing]
installer:
  type: exe
  location: pkgs/apps/browsers/ExampleBrowser-136.0.exe
  hash: {HASH}
notes: Duplicate on purpose.
""",
    # Comments, quoted versions, PowerShell, dependencies, unknown keys, large integers.
    "pkgsinfo/apps/creative/ExampleEditor-2.10.yaml": f"""\
# Hand-maintained pkginfo; comments must survive edits.
name: ExampleEditor
display_name: Example Editor
version: "2.10"   # quoted: must stay a string, not 2.1
category: Creative
developer: Example Co
description: Invented editor package for tests.

catalogs:
  - testing
  - production

requires:
  - ExampleRuntime

installer:
  type: msi
  location: pkgs/apps/creative/ExampleEditor-2.10.msi
  hash: {HASH}
  arguments:
    - /qn
    - /norestart

installs:
  - type: msi
    product_code: "{{00000000-0000-0000-0000-000000000001}}"

uninstaller:
  - type: msi
    product_code: "{{00000000-0000-0000-0000-000000000001}}"

supported_architectures: [x64, arm64]
minimum_os_version: 10.0.19045
blocking_applications:
  - editor.exe

preinstall_script: |
  # PowerShell, runs before install
  $path = "$env:ProgramData\\Example"
  if (-not (Test-Path $path)) {{ New-Item -ItemType Directory -Path $path | Out-Null }}

installed_size: 9007199254740993
x_unknown_site_key:
  nested: [1, 2.5, three]
""",
    "pkgsinfo/apps/creative/ExampleEditorPlugin-1.0.yaml": f"""\
name: ExampleEditorPlugin
version: "1.0"
category: Creative
catalogs:
  - testing
update_for:
  - ExampleEditor
installer:
  type: nupkg
  location: pkgs/apps/creative/ExampleEditorPlugin-1.0.nupkg
  hash: {HASH}
""",
    "pkgsinfo/apps/creative/ExampleViewer-1.0.yaml": f"""\
name: ExampleViewer
version: "1.0"
category: Creative
catalogs: [testing, production]
installer:
  type: msix
  location: pkgs/apps/creative/ExampleViewer-1.0.msix
  hash: {HASH}
""",
    "pkgsinfo/tools/ExampleRuntime-5.0.yaml": f"""\
name: ExampleRuntime
version: "5.0"
category: Utilities
catalogs:
  - testing
  - production
installer:
  type: exe
  location: pkgs/tools/ExampleRuntime-5.0.exe
  hash: {HASH}
  arguments: ["/quiet"]
""",
    "pkgsinfo/tools/ExampleScript-1.0.yaml": """\
name: ExampleScript
version: "1.0"
category: Utilities
catalogs:
  - testing
installer:
  type: ps1
  location: pkgs/tools/ExampleScript-1.0.ps1
installcheck_script: |
  if (Test-Path "C:\\ProgramData\\Example\\done.txt") { exit 1 }
  exit 0
""",
    # Invalid inputs: broken indentation, and a root that is not a mapping.
    "pkgsinfo/invalid/Broken-1.0.yaml": """\
name: Broken
version: "1.0"
  catalogs:
 - testing
""",
    "pkgsinfo/invalid/NotAMapping-1.0.yaml": """\
- not
- a
- mapping
""",
    "manifests/site_default.yaml": """\
display_name: Site Default
catalogs:
  - production
managed_installs:
  - ExampleBrowser
  - ExampleRuntime
""",
    "manifests/groups/design-lab.yaml": """\
display_name: Design Lab
catalogs:
  - testing
  - production

included_manifests:
  - site_default

managed_installs:
  - ExampleEditor   # all lab machines
  - ExampleViewer
optional_installs:
  - ExampleScript
managed_uninstalls:
  - ExampleLegacy

conditional_items:
  - condition: "hostname contains 'LAB-' AND arch == 'arm64'"
    managed_installs:
      - ExampleEditorPlugin

  - fact: department
    operator: "=="
    value: "IT"
    managed_installs:
      - ExampleRuntime

notes: |
  Invented manifest.
  Conditional items use both supported forms.
""",
    # Missing references: nothing is named ExampleMissing, and the include does not exist.
    "manifests/groups/broken-refs.yaml": """\
catalogs: [testing]
included_manifests:
  - groups/does-not-exist
managed_installs:
  - ExampleMissing
""",
    # Include cycle: loop-a includes loop-b, which includes loop-a.
    "manifests/groups/loop-a.yaml": "catalogs: [testing]\nincluded_manifests:\n  - groups/loop-b\n",
    "manifests/groups/loop-b.yaml": "catalogs: [testing]\nincluded_manifests:\n  - groups/loop-a\n",
    "manifests/computers/EXAMPLE-0001.yaml": """\
catalogs:
  - testing
  - production
included_manifests:
  - groups/design-lab
""",
}


def build() -> None:
    if REPO.exists():
        shutil.rmtree(REPO)
    for relative, text in FILES.items():
        path = REPO / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    for folder in ("pkgs", "icons", "catalogs"):
        (REPO / folder).mkdir(parents=True, exist_ok=True)
        (REPO / folder / ".gitkeep").write_text("")


if __name__ == "__main__":
    build()
