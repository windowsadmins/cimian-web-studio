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
installed in `C:\Program Files\Cimian`. The worker installer and its steps are
described in the next section once it is built.

