# Cimian Web Studio

This is a new project for a ground-up web application for Cimian repositories,
inspired by CimianStudio. It does not replace the native CimianStudio app.

## Project state

Planning only. Read `docs/plan.md`, `docs/architecture.md`,
`docs/infrastructure.md`, and `docs/design.md` before implementation.
Recommendations in those documents remain proposals until explicitly accepted.
Do not describe the design prototype as a functioning repository editor.

## Worktrees and delivery

Create task worktrees inside `./.worktrees/` with the global `git wt` alias,
starting from `origin/main`. Keep `/.worktrees/` ignored. Use task branches
and reviewed pull requests. Never add assistant attribution or bracketed tags
to commit subjects. Track project work in this repository's GitHub issues.

## Repository integrity

Use synthetic fixtures. Never attach a live Cimian repository during development
without explicit authorization. Preserve unknown YAML keys, scalar types and
quoting of version strings, key order, comments where the codec allows, relative
paths, and meaningful list order. Do not silently reformat files or make Git
mandatory. Catalogs are derived outputs of `makecatalogs`.

## Standalone, and hostable

Cimian Web Studio is a complete product with no dependency on any other
repository. It must run on its own for an admin who has never heard of Munki.
Never import from `rodchristiansen/fleetmate-web-admin` or
`rodchristiansen/munki-web-studio`.

FleetMate Web Admin hosts this studio alongside Munki Web Studio for admins
who run both. It depends on this repository, never the reverse. Keep the hosting
surface in `docs/hosting.md` working, and keep `docs/hosting.md` and
`docs/backend.md` identical to their copies in Munki Web Studio.

Workspace, change-set, job, Git and audit code is copied between the two studios,
not shared. When you fix it here, open the matching pull request in Munki Web
Studio.

## Infrastructure

All deployable configuration belongs in versioned IaC and the reviewed deployment
path. Planning does not authorize cloud provisioning or identity changes.
Keep application state, repository content, credentials, and package payloads
out of this source repository. Licensed MIT (`LICENSE`).
