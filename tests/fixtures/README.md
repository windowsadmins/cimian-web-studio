# Test fixtures

Every value here is invented. Never add data copied from a real repository.

## `repo/`

A small Cimian repository with the real layout (`pkgsinfo`, `manifests`,
`catalogs`, `pkgs`, `icons`), all YAML. It covers the cases later slices test:

| Case | Where |
| --- | --- |
| Nested pkginfo directories | `pkgsinfo/apps/*`, `pkgsinfo/tools` |
| Several versions of one name | `ExampleBrowser` 135.0 and 136.0 |
| Same name and version in two files | `apps/browsers` and `apps/browsers/duplicates` |
| Comments, quoted versions, blank lines | `ExampleEditor-2.10.yaml` |
| PowerShell scripts, Windows paths | `ExampleEditor`, `ExampleScript`, `ExampleBrowser` |
| msi, exe, msix, nupkg, ps1 installers | across `pkgsinfo` |
| Dependencies, unknown keys, large integers, zero hash | `ExampleEditor`, `ExampleEditorPlugin` |
| Invalid files | `pkgsinfo/invalid` |
| A `condition:` string, and the fact/operator/value form Cimian clients ignore | `manifests/groups/design-lab.yaml` |
| Missing references | `manifests/groups/broken-refs.yaml` |
| Include cycle | `manifests/groups/loop-a.yaml` and `loop-b.yaml` |

`build_repo_fixture.py` writes the repository as text, so comments and quoting
are exactly as written. Rebuild it from the repository root:

```sh
python3 -I tests/fixtures/build_repo_fixture.py
```

`catalogs/` is empty for now. The catalogs slice (S26) fills it with real
Cimian `makecatalogs` output, generated on Windows.

## `codec/`

The single files from the codec spike, used by codec round-trip tests.

## Large repository

`generate_large_repo.py` writes a repository of any size for benchmarks. It is
deterministic for a given seed. The default is 10,000 pkginfo and 2,000
manifests:

```sh
python3 -I tests/fixtures/generate_large_repo.py /tmp/large-cimian-repo
```
