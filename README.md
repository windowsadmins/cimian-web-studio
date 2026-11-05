# Cimian Web Studio

A ground-up web workspace for [Cimian](https://github.com/windowsadmins/cimian)
repositories, inspired by
[CimianStudio](https://github.com/windowsadmins/cimian-studio).

Cimian Web Studio runs on its own; it needs nothing from Munki or any other
project. Admins who manage both Cimian and Munki can run it alongside
[Munki Web Studio](https://github.com/rodchristiansen/munki-web-studio) in
[FleetMate Web Admin](https://github.com/rodchristiansen/fleetmate-web-admin),
which hosts both studios in one app. See [standalone and hosted](docs/hosting.md).

Browse packages, edit pkginfo and manifests, understand conditional items and
dependencies, review changes, and publish through an explicit workflow. Existing
repository YAML remains authoritative.

**Status: planning and design exploration. There is no application backend yet.**

## Start here

- [Build plan](docs/build-plan.md)
- [Product plan and milestones](docs/plan.md)
- [Architecture and compatibility boundaries](docs/architecture.md)
- [Infrastructure options and deployment requirements](docs/infrastructure.md)
- [Design direction and interaction specification](docs/design.md)
- [Backend language and why](docs/backend.md)
- [Standalone and hosted](docs/hosting.md)
- [MCP server for AI agents](docs/mcp.md)
- [Command line](docs/cli.md)
- [Reference research](docs/research.md)
- [Interactive workspace study](docs/design/workspace.html)

The workspace study uses invented sample data and runs locally without a build
step. To serve it, run this from the repository root:

```sh
python3 -m http.server 3187 --bind 127.0.0.1
```

Then open <http://127.0.0.1:3187/docs/design/workspace.html>.

The proposed starting point is a self-hosted web app with a repository service
and an optional Windows worker for Cimian's Windows-only tools. Deployment,
framework, identity provider, and licensing choices remain open. No cloud
resources have been provisioned.

## Command line

`cwsctl` works on a repository folder directly, with no server. Find packages
and manifests:

```sh
cwsctl search editor --repo /path/to/repo
```

Print one file, or list what refers to a package:

```sh
cwsctl show pkgsinfo/apps/Editor-2.10.yaml --repo /path/to/repo
```

```sh
cwsctl where-used Editor --repo /path/to/repo
```

Check the whole repository. The command exits 1 when it finds errors, so a
repository's CI can run it on every pull request; `--strict` fails on warnings
too, and `--json` prints a machine-readable report:

```sh
cwsctl validate --repo /path/to/repo
```

## Development

The backend is a Python 3.14 package managed with [uv](https://docs.astral.sh/uv/).
Install the dependencies from the lockfile:

```sh
uv sync
```

Run the linters, type checker, and tests:

```sh
uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest
```

Start the web app, API, and MCP server on <http://127.0.0.1:3186>:

```sh
uv run cwsctl serve
```

The health check is at `/api/health` and the MCP server at `/mcp`.

The browser workspace lives in `web/` (React, TypeScript, Vite, pnpm). Build it
into the Python package so `cwsctl serve` serves it at `/`:

```sh
cd web && pnpm install && pnpm build
```

Run its type check, component tests, and the browser test against the real
server:

```sh
pnpm typecheck && pnpm test && pnpm e2e
```

The browser talks to the API through a client generated from `web/openapi.json`.
After changing an API route or model, regenerate both from the repository root:

```sh
uv run cwsctl openapi --output web/openapi.json && (cd web && pnpm gen:api)
```

CI fails when either file is out of date.

For live reloading, run `uv run cwsctl serve` and `pnpm dev` side by side; the
Vite dev server forwards `/api` and `/mcp` to the API.
