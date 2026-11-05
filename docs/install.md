# Installing Cimian Web Studio on one host

This sets up the studio with Docker Compose on a single host, reading a Cimian
repository that is already there, plus an optional Windows worker for the jobs
that need Cimian's own tools. Nothing here needs a cloud account.

## The studio

You need Docker with the Compose plugin, and a Cimian repository folder on the
host.

Make a folder for the deployment, and copy in the Compose file and the example
config from this repository's `deploy/` folder:

```sh
mkdir cimian-web-studio && cd cimian-web-studio
```

```sh
curl -fsSLO https://raw.githubusercontent.com/windowsadmins/cimian-web-studio/main/deploy/compose.yaml
```

```sh
curl -fsSLO https://raw.githubusercontent.com/windowsadmins/cimian-web-studio/main/deploy/studio.toml
```

Create `.env` with the image and the repository folder. Use the image digest
listed in the release you are installing, never a moving tag:

```sh
printf 'STUDIO_IMAGE=ghcr.io/windowsadmins/cimian-web-studio@sha256:<digest>\nCIMIAN_REPO=/srv/cimian-repo\n' > .env
```

Start it, and wait until Compose reports the container healthy:

```sh
docker compose up -d --wait
```

The studio now answers on <http://127.0.0.1:3186>, on this host only. What the
deployment does:

- The repository is mounted read-only at `/srv/cimian`, and `studio.toml` says
  `writable = false`. To edit, point `CIMIAN_REPO` at an authoring copy and
  change both: `:rw` on the mount, and `writable = true` in the config.
- Drafts, jobs, sessions, uploads, the audit log and the search index live
  on the `studio-state` volume. Back it up. It holds no repository content.
- The container runs as UID 10001 with a read-only root filesystem, all
  capabilities dropped, and no privilege escalation.

To serve other machines, set up sign-in (`[auth]`) in `studio.toml`, add the
host name to `allowed_hosts`, remove `CIMIAN_WEB_STUDIO_ALLOW_UNAUTHENTICATED`
from `compose.yaml`, and put a TLS reverse proxy in front. Without sign-in the
studio refuses to start on a non-loopback address unless that variable is set,
so `docker run -p 3186:3186` with the image alone does not expose an open
studio.

To upgrade, change `STUDIO_IMAGE` to the new release's digest and run
`docker compose up -d --wait` again.

## The Windows worker (optional)

Catalog generation and package import run on a Windows machine with Cimian
installed in `C:\Program Files\Cimian`. Build the installer on a Windows machine
with `uv` and `pnpm`, from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build-worker-zip.ps1
```

It writes `dist\CimianWebStudioWorker-0.1.0-win-x64.zip`. The zip holds the
worker, with its own Python, plus `install.ps1` and `uninstall.ps1`. Nothing in
it is signed, so check where it came from before you install it.

The worker installs to `C:\Program Files\Cimian Web Studio Worker`. Its config,
token and log live in `C:\ProgramData\Cimian Web Studio Worker`, which only
SYSTEM, Administrators and the worker can read. A scheduled task,
`\Cimian Web Studio\Worker`, starts it at boot as `NT AUTHORITY\LOCAL SERVICE`,
never as SYSTEM or an administrator.

Make a token for the worker on any machine with `cwsctl`. Add the
`[[workers]]` lines it prints to `studio.toml`:

```powershell
cwsctl worker token --id win-1
```

On the Windows machine, save the token in a file that only you can read, such
as `C:\Users\you\win-1.token`. Then unpack the zip:

```powershell
Expand-Archive CimianWebStudioWorker-0.1.0-win-x64.zip C:\Temp\cws-worker
```

From an elevated PowerShell, install the worker with the studio's address, the
worker id and the token file:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Temp\cws-worker\install.ps1 -Url https://studio.example.org -Id win-1 -TokenFile C:\Users\you\win-1.token
```

The installer copies the token into the worker's own folder, so delete your
copy:

```powershell
Remove-Item C:\Users\you\win-1.token
```

Settings in the studio shows the worker as connected, with its Cimian tool
versions. Its log is `C:\ProgramData\Cimian Web Studio Worker\logs\worker.log`.
To change the address or id later, edit `worker.conf` in the same folder. The
worker reads it each time it connects.

Package import does not work yet with an unelevated worker.
`makepkginfo.exe` 2026.10.28 reads `Config.yaml` before it starts, and only
administrators can read that file, so every import fails. Catalog generation
is not affected.

To upgrade, unpack the new zip and run `install.ps1` again. The config and
token stay. To remove the worker, run its uninstaller from an elevated
PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Program Files\Cimian Web Studio Worker\uninstall.ps1"
```

This keeps the config and token. To delete them as well, add `-RemoveData`.

