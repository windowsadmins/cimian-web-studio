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
